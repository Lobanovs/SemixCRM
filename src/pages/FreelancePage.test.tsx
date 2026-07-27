import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import FreelancePage from './FreelancePage'

const sourceKeys = ['kwork', 'fl', 'freelance_ru', 'profi', 'youdo']

const settings = {
  sources: sourceKeys,
  keywords: [],
  excluded_keywords: [],
  categories: [],
  min_budget: 0,
  interval_seconds: 60,
  sniper_enabled: false,
  telegram_enabled: false,
}

const sourceStatuses = [
  { source: 'kwork', status: 'error', error: 'Временная ошибка сети' },
  { source: 'fl', status: 'done', order_count: 30 },
  { source: 'freelance_ru', status: 'empty', order_count: 0 },
  { source: 'profi', status: 'auth_required', auth_required: true, error: 'Нужно войти' },
  { source: 'youdo', status: 'done', order_count: 500 },
]

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

    if (method === 'GET' && url.includes('/api/freelance/orders')) {
      return jsonResponse({ orders: [], stats: { total: 42, responded: 0, replied: 0, in_progress: 0, new_today: 0, archived: 0, stages: {} }, relevance_max: 20 })
    }
    if (method === 'GET' && url.endsWith('/api/freelance/settings')) return jsonResponse(settings)
    if (method === 'GET' && url.endsWith('/api/freelance/sources')) return jsonResponse({ sources: sourceStatuses })
    if (method === 'GET' && url.endsWith('/api/freelance/sniper/status')) return jsonResponse({ status: 'stopped', sources: {}, interval_seconds: 60 })
    if (method === 'PUT' && url.endsWith('/api/freelance/settings')) return jsonResponse(JSON.parse(String(init?.body || '{}')))
    if (method === 'POST' && url.endsWith('/api/freelance/orders/cleanup')) {
      const body = JSON.parse(String(init?.body || '{}'))
      if (body.preview) {
        return jsonResponse({
          preview: true,
          matched: body.max_relevance === 40 ? 12 : body.older_than_days === 7 ? 4 : 0,
          kept: 30,
          sample: [{ title: 'Собрать мебель', relevance: 0, source: 'youdo' }],
        })
      }
      return jsonResponse({ preview: false, archived_count: 12, stats: { total: 30, responded: 0, replied: 0, in_progress: 0, new_today: 0, archived: 12, stages: {} } })
    }
    if (method === 'POST' && url.endsWith('/api/freelance/orders/restore-all')) {
      return jsonResponse({ ok: true, restored_count: 12, stats: { total: 42, responded: 0, replied: 0, in_progress: 0, new_today: 0, archived: 0, stages: {} } })
    }
    if (method === 'POST' && url.endsWith('/api/freelance/sniper/check')) return jsonResponse({ status: 'done' })
    if (method === 'POST' && /\/api\/freelance\/sources\/(profi|youdo)\/auth$/.test(url)) return jsonResponse({ status: 'opened' })
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
}

describe('freelance source controls', () => {
  beforeEach(() => vi.stubGlobal('fetch', createFetchMock()))

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('shows five recognizable source badges without Workzilla', async () => {
    render(<FreelancePage />)
    await screen.findByRole('heading', { name: 'Фриланс' })

    for (const label of ['Kwork', 'FL.ru', 'Freelance.ru', 'Profi.ru', 'YouDo']) {
      expect(screen.getAllByRole('img', { name: `${label} — значок источника` }).length).toBeGreaterThan(0)
    }
    expect(screen.queryByText('Workzilla')).not.toBeInTheDocument()
  })

  it('offers clear recovery actions for authorization and transient errors', async () => {
    const user = userEvent.setup()
    render(<FreelancePage />)

    await user.click(await screen.findByRole('button', { name: 'Войти в Profi.ru' }))
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => init?.method === 'POST' && String(url).endsWith('/sources/profi/auth'))).toBe(true))

    await user.click(screen.getByRole('button', { name: 'Повторить проверку Kwork' }))
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => init?.method === 'POST' && String(url).endsWith('/sniper/check'))).toBe(true))
  })

  it('saves settings with exactly the five supported sources', async () => {
    const user = userEvent.setup()
    render(<FreelancePage />)
    await user.click(await screen.findByRole('button', { name: 'Настроить' }))

    const dialog = screen.getByRole('dialog', { name: 'Настройки снайпера' })
    expect(within(dialog).getAllByRole('checkbox', { name: /Kwork|FL\.ru|Freelance\.ru|Profi\.ru|YouDo/ })).toHaveLength(5)
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить настройки' }))

    await waitFor(() => {
      const saveCall = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'PUT' && String(url).endsWith('/api/freelance/settings'))
      expect(saveCall).toBeDefined()
      expect(JSON.parse(String(saveCall?.[1]?.body)).sources).toEqual(sourceKeys)
    })
  })

  it('открывает уборку списка и показывает, сколько заказов уйдёт', async () => {
    const user = userEvent.setup()
    render(<FreelancePage />)

    await user.click(await screen.findByRole('button', { name: /Очистить список/ }))

    const dialog = await screen.findByRole('dialog', { name: 'Очистить список заказов' })
    // Текст разбит на несколько узлов, поэтому сверяем содержимое блока целиком.
    await waitFor(() => expect(dialog.querySelector('.cleanup-preview')?.textContent).toContain('Будет скрыто: 12 из 42'))
    expect(dialog.querySelector('.cleanup-preview')?.textContent).toContain('Собрать мебель')
  })

  it('пресет «Залежавшиеся» пересчитывает предпросмотр по возрасту', async () => {
    const user = userEvent.setup()
    render(<FreelancePage />)
    await user.click(await screen.findByRole('button', { name: /Очистить список/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Очистить список заказов' })

    await user.click(within(dialog).getByRole('button', { name: /Залежавшиеся/ }))

    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.findLast(([url, init]) => init?.method === 'POST' && String(url).endsWith('/orders/cleanup'))
      expect(JSON.parse(String(call?.[1]?.body)).older_than_days).toBe(7)
    })
    await waitFor(() => expect(dialog.querySelector('.cleanup-preview')?.textContent).toContain('Будет скрыто: 4 из 42'))
  })

  it('предпросмотр ничего не скрывает до подтверждения', async () => {
    const user = userEvent.setup()
    render(<FreelancePage />)
    await user.click(await screen.findByRole('button', { name: /Очистить список/ }))
    await screen.findByRole('dialog', { name: 'Очистить список заказов' })

    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/orders/cleanup'))).toBe(true))
    const applied = vi.mocked(fetch).mock.calls
      .filter(([url, init]) => init?.method === 'POST' && String(url).endsWith('/orders/cleanup'))
      .filter(([, init]) => JSON.parse(String(init?.body)).preview === false)
    expect(applied).toHaveLength(0)
  })

  it('подтверждение отправляет уборку и защитный заголовок', async () => {
    const user = userEvent.setup()
    render(<FreelancePage />)
    await user.click(await screen.findByRole('button', { name: /Очистить список/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Очистить список заказов' })

    await user.click(await within(dialog).findByRole('button', { name: /Скрыть 12 заказов/ }))

    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.findLast(([url, init]) =>
        init?.method === 'POST' && String(url).endsWith('/orders/cleanup')
        && JSON.parse(String(init?.body)).preview === false)
      expect(call).toBeDefined()
      expect((call?.[1]?.headers as Record<string, string>)['X-Requested-With']).toBe('SemixCRM')
    })
  })
})
