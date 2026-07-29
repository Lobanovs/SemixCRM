import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import UsefulThingsPage from './UsefulThingsPage'


type UsefulLink = {
  id: number
  title: string
  url: string
  description: string
  created_at: string
  updated_at: string
}

const INITIAL_LINKS: UsefulLink[] = [
  {
    id: 1,
    title: 'Figma',
    url: 'https://figma.com',
    description: 'Макеты и прототипы интерфейсов',
    created_at: '2026-07-29T10:00:00+00:00',
    updated_at: '2026-07-29T10:00:00+00:00',
  },
  {
    id: 2,
    title: 'MDN',
    url: 'https://developer.mozilla.org',
    description: 'Документация по веб-технологиям',
    created_at: '2026-07-29T11:00:00+00:00',
    updated_at: '2026-07-29T11:00:00+00:00',
  },
]

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function createUsefulFetch(options: { failPost?: string; initial?: UsefulLink[] } = {}) {
  let items = [...(options.initial ?? INITIAL_LINKS)]
  let nextId = Math.max(0, ...items.map((item) => item.id)) + 1
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'
    if (method === 'GET' && url.endsWith('/api/useful-links')) {
      return jsonResponse({ items, stats: { total: items.length } })
    }
    if (method === 'POST' && url.endsWith('/api/useful-links')) {
      if (options.failPost) return jsonResponse({ detail: options.failPost }, 422)
      const body = JSON.parse(String(init?.body)) as Pick<UsefulLink, 'title' | 'url' | 'description'>
      const item: UsefulLink = {
        ...body,
        id: nextId++,
        url: body.url.startsWith('http') ? body.url : `https://${body.url}`,
        created_at: '2026-07-29T12:00:00+00:00',
        updated_at: '2026-07-29T12:00:00+00:00',
      }
      items = [item, ...items]
      return jsonResponse(item, 201)
    }
    const match = url.match(/\/api\/useful-links\/(\d+)$/)
    if (method === 'PUT' && match) {
      const body = JSON.parse(String(init?.body)) as Pick<UsefulLink, 'title' | 'url' | 'description'>
      const id = Number(match[1])
      const current = items.find((item) => item.id === id)
      if (!current) return jsonResponse({ detail: 'Полезный сайт не найден' }, 404)
      const updated = { ...current, ...body, updated_at: '2026-07-29T13:00:00+00:00' }
      items = items.map((item) => item.id === id ? updated : item)
      return jsonResponse(updated)
    }
    if (method === 'DELETE' && match) {
      const id = Number(match[1])
      items = items.filter((item) => item.id !== id)
      return jsonResponse({ ok: true, deleted_id: id })
    }
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
}

describe('раздел «Полезные вещи»', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('загружает полезные сайты и даёт безопасно открыть их', async () => {
    vi.stubGlobal('fetch', createUsefulFetch())

    render(<UsefulThingsPage />)

    expect(await screen.findByRole('heading', { name: 'Полезные вещи', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Макеты и прототипы интерфейсов')).toBeInTheDocument()
    expect(screen.getByText('developer.mozilla.org')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Открыть Figma' })).toHaveAttribute('href', 'https://figma.com')
    expect(screen.getByRole('link', { name: 'Открыть Figma' })).toHaveAttribute('rel', 'noreferrer')
  })

  it('фильтрует каталог локально по описанию', async () => {
    const user = userEvent.setup()
    const fetchMock = createUsefulFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<UsefulThingsPage />)
    await screen.findByText('Figma')

    await user.type(screen.getByLabelText('Поиск по полезным сайтам'), 'документация')

    expect(screen.queryByText('Figma')).not.toBeInTheDocument()
    expect(screen.getByText('MDN')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('добавляет сайт через подписанную форму', async () => {
    const user = userEvent.setup()
    const fetchMock = createUsefulFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<UsefulThingsPage />)
    await screen.findByText('Figma')

    await user.click(screen.getByRole('button', { name: 'Добавить сайт' }))
    const dialog = screen.getByRole('dialog', { name: 'Добавить полезный сайт' })
    await user.type(within(dialog).getByLabelText('Название'), 'Notion')
    await user.type(within(dialog).getByLabelText('Адрес сайта'), 'notion.so')
    await user.type(within(dialog).getByLabelText('Описание'), 'База знаний и заметки')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить сайт' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Сайт добавлен')
    expect(screen.getByText('Notion')).toBeInTheDocument()
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      title: 'Notion',
      url: 'notion.so',
      description: 'База знаний и заметки',
    })
    expect((postCall?.[1]?.headers as Record<string, string>)['X-Requested-With']).toBe('SemixCRM')
  })

  it('редактирует существующую карточку', async () => {
    const user = userEvent.setup()
    const fetchMock = createUsefulFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<UsefulThingsPage />)
    const card = await screen.findByRole('article', { name: 'Сайт Figma' })

    await user.click(within(card).getByRole('button', { name: 'Изменить Figma' }))
    const dialog = screen.getByRole('dialog', { name: 'Изменить сайт' })
    const description = within(dialog).getByLabelText('Описание')
    await user.clear(description)
    await user.type(description, 'Совместная работа над макетами')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить изменения' }))

    expect(await screen.findByText('Совместная работа над макетами')).toBeInTheDocument()
    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(String(putCall?.[0])).toMatch(/\/api\/useful-links\/1$/)
    expect(JSON.parse(String(putCall?.[1]?.body))).toMatchObject({
      title: 'Figma',
      url: 'https://figma.com',
      description: 'Совместная работа над макетами',
    })
  })

  it('удаляет сайт только после явного подтверждения', async () => {
    const user = userEvent.setup()
    const fetchMock = createUsefulFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<UsefulThingsPage />)
    const card = await screen.findByRole('article', { name: 'Сайт Figma' })

    await user.click(within(card).getByRole('button', { name: 'Удалить Figma' }))
    const dialog = screen.getByRole('dialog', { name: 'Удалить Figma?' })
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
    await user.click(within(dialog).getByRole('button', { name: 'Удалить сайт' }))

    await waitFor(() => expect(screen.queryByText('Макеты и прототипы интерфейсов')).not.toBeInTheDocument())
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(true)
  })

  it('показывает ошибку сохранения как доступный alert', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createUsefulFetch({ failPost: 'Этот сайт уже добавлен' }))
    render(<UsefulThingsPage />)
    await screen.findByText('Figma')

    await user.click(screen.getByRole('button', { name: 'Добавить сайт' }))
    const dialog = screen.getByRole('dialog', { name: 'Добавить полезный сайт' })
    await user.type(within(dialog).getByLabelText('Название'), 'Figma снова')
    await user.type(within(dialog).getByLabelText('Адрес сайта'), 'figma.com')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить сайт' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Этот сайт уже добавлен')
  })
})
