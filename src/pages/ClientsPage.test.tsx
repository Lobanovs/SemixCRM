import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ClientsPage from './ClientsPage'


const settings = {
  city: 'Москва',
  niches: ['стоматологии'],
  sources: ['2gis'],
  limit: 10,
  start_page: 1,
  updated_at: '2026-07-22T12:00:00Z',
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function createFetchMock() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'

    if (method === 'GET' && url.endsWith('/api/clients')) {
      return jsonResponse({
        clients: [],
        stats: {
          total: 0, contacted: 0, replied: 0, calls: 0, closed: 0,
          found_today: 0, new_today: 0,
          stages: { Новый: 0, Написал: 0, Ответили: 0, Созвон: 0, КП: 0, Закрыто: 0, Отказ: 0 },
        },
      })
    }
    if (method === 'GET' && url.endsWith('/api/parser/settings')) return jsonResponse(settings)
    if (method === 'GET' && url.includes('/api/parser/runs')) return jsonResponse({ runs: [] })
    if (method === 'GET' && url.endsWith('/api/clients/archived')) return jsonResponse({ clients: [] })
    if (method === 'PUT' && url.endsWith('/api/parser/settings')) {
      return jsonResponse({ ...settings, ...JSON.parse(String(init?.body || '{}')) })
    }
    if (method === 'POST' && url.endsWith('/api/clients/parse')) {
      return jsonResponse({ job_id: '', error: 'Диагностическая остановка после проверки порядка запросов' })
    }
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
}

describe('client parser controls', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', createFetchMock())
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('shows the 2GIS start page without opening a settings modal', async () => {
    render(<ClientsPage />)

    await screen.findByRole('heading', { name: 'Парсер клиентов' })

    expect(screen.queryByRole('spinbutton', { name: 'Стартовая страница 2GIS' })).toBeVisible()
  })

  it('saves the visible start page in parser settings', async () => {
    const user = userEvent.setup()
    render(<ClientsPage />)
    const pageInput = await screen.findByRole('spinbutton', { name: 'Стартовая страница 2GIS' })
    await waitFor(() => expect(pageInput).toBeEnabled())

    await user.clear(pageInput)
    await user.type(pageInput, '4')
    await user.click(screen.getByRole('button', { name: 'Сохранить настройки' }))

    const fetchMock = vi.mocked(fetch)
    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/api/parser/settings') && init?.method === 'PUT')
      expect(saveCall).toBeDefined()
      expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({ start_page: 4 })
    })
  })

  it('saves current settings before starting the parser', async () => {
    const user = userEvent.setup()
    const baseFetch = createFetchMock()
    const normalizingFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'PUT' && String(input).endsWith('/api/parser/settings')) {
        return jsonResponse({ ...settings, ...JSON.parse(String(init.body || '{}')), start_page: 9 })
      }
      return baseFetch(input, init)
    })
    vi.stubGlobal('fetch', normalizingFetch)
    render(<ClientsPage />)
    await screen.findByRole('heading', { name: 'Парсер клиентов' })

    const runButton = screen.getByRole('button', { name: 'Запустить парсер' })
    await waitFor(() => expect(runButton).toBeEnabled())
    await user.click(runButton)

    await waitFor(() => {
      const mutations = normalizingFetch.mock.calls
        .filter(([, init]) => init?.method === 'PUT' || init?.method === 'POST')
        .map(([url, init]) => `${init?.method} ${new URL(String(url)).pathname}`)
      expect(mutations.slice(0, 2)).toEqual([
        'PUT /api/parser/settings',
        'POST /api/clients/parse',
      ])
      const startCall = normalizingFetch.mock.calls.find(([url, init]) => String(url).endsWith('/api/clients/parse') && init?.method === 'POST')
      expect(JSON.parse(String(startCall?.[1]?.body))).toMatchObject({ start_page: 9 })
    })
  })

  it('does not start parsing when settings cannot be saved', async () => {
    const user = userEvent.setup()
    const baseFetch = createFetchMock()
    const failingFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'PUT' && String(input).endsWith('/api/parser/settings')) {
        return jsonResponse({ detail: 'Настройки отклонены backend' }, 422)
      }
      return baseFetch(input, init)
    })
    vi.stubGlobal('fetch', failingFetch)
    render(<ClientsPage />)
    await screen.findByRole('heading', { name: 'Парсер клиентов' })

    const runButton = screen.getByRole('button', { name: 'Запустить парсер' })
    await waitFor(() => expect(runButton).toBeEnabled())
    await user.click(runButton)

    expect(await screen.findByRole('alert')).toHaveTextContent('Настройки отклонены backend')
    expect(failingFetch.mock.calls.some(([url, init]) => init?.method === 'POST' && String(url).endsWith('/api/clients/parse'))).toBe(false)
  })

  it('locks parser actions until saved settings finish loading', async () => {
    let resolveSettings!: (response: Response) => void
    const pendingSettings = new Promise<Response>((resolve) => { resolveSettings = resolve })
    const baseFetch = createFetchMock()
    const delayedFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (!init?.method && String(input).endsWith('/api/parser/settings')) return pendingSettings
      return baseFetch(input, init)
    })
    vi.stubGlobal('fetch', delayedFetch)
    render(<ClientsPage />)

    const runButton = screen.getByRole('button', { name: 'Запустить парсер' })
    expect(runButton).toBeDisabled()
    expect(screen.getByText('Загружаю сохранённые настройки')).toBeVisible()

    await act(async () => { resolveSettings(jsonResponse(settings)) })
    await waitFor(() => expect(runButton).toBeEnabled())
  })

  it('explains why parsing is disabled when no source is selected', async () => {
    const user = userEvent.setup()
    render(<ClientsPage />)
    const sourceButton = await screen.findByRole('button', { name: '2GIS' })
    await waitFor(() => expect(sourceButton).toBeEnabled())

    await user.click(sourceButton)

    expect(screen.getByRole('alert')).toHaveTextContent('Выберите хотя бы один источник')
    expect(screen.getByRole('button', { name: 'Запустить парсер' })).toBeDisabled()
  })

  it('restores focus to niche selection after closing its dialog', async () => {
    const user = userEvent.setup()
    render(<ClientsPage />)
    const chooseButton = await screen.findByRole('button', { name: 'Выбрать' })
    await waitFor(() => expect(chooseButton).toBeEnabled())
    await user.click(chooseButton)
    expect(screen.getByRole('textbox', { name: 'Поиск ниши' })).toHaveFocus()

    await user.keyboard('{Escape}')

    await waitFor(() => expect(chooseButton).toHaveFocus())
    expect(screen.queryByRole('dialog', { name: 'Выберите ниши' })).not.toBeInTheDocument()
  })
})
