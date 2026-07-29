import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import UsefulThingsPage from './UsefulThingsPage'

const PAGE_CSS = readFileSync(resolve(process.cwd(), 'src/pages/UsefulThingsPage.css'), 'utf8')

type UsefulCategory = 'prompt' | 'website' | 'shop' | 'article' | 'other'

type UsefulLink = {
  id: number
  title: string
  category: UsefulCategory
  url: string
  description: string
  created_at: string
  updated_at: string
}

const INITIAL_LINKS: UsefulLink[] = [
  {
    id: 1,
    title: 'Figma',
    category: 'website',
    url: 'https://figma.com',
    description: 'Макеты и прототипы интерфейсов',
    created_at: '2026-07-29T10:00:00+00:00',
    updated_at: '2026-07-29T10:00:00+00:00',
  },
  {
    id: 2,
    title: 'MDN',
    category: 'article',
    url: 'https://developer.mozilla.org',
    description: 'Документация по веб-технологиям',
    created_at: '2026-07-29T11:00:00+00:00',
    updated_at: '2026-07-29T11:00:00+00:00',
  },
  {
    id: 3,
    title: 'Аудит лендинга',
    category: 'prompt',
    url: '',
    description: 'Проанализируй первый экран лендинга и найди точки роста.',
    created_at: '2026-07-29T11:30:00+00:00',
    updated_at: '2026-07-29T11:30:00+00:00',
  },
  {
    id: 4,
    title: 'UI8',
    category: 'shop',
    url: 'https://ui8.net',
    description: 'Хороший магазин UI-наборов',
    created_at: '2026-07-29T11:45:00+00:00',
    updated_at: '2026-07-29T11:45:00+00:00',
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
      return jsonResponse({ items, stats: { total: items.length, categories: {} } })
    }
    if (method === 'POST' && url.endsWith('/api/useful-links')) {
      if (options.failPost) return jsonResponse({ detail: options.failPost }, 422)
      const body = JSON.parse(String(init?.body)) as Pick<UsefulLink, 'title' | 'category' | 'url' | 'description'>
      const item: UsefulLink = {
        ...body,
        id: nextId++,
        url: !body.url || body.url.startsWith('http') ? body.url : `https://${body.url}`,
        created_at: '2026-07-29T12:00:00+00:00',
        updated_at: '2026-07-29T12:00:00+00:00',
      }
      items = [item, ...items]
      return jsonResponse(item, 201)
    }
    const match = url.match(/\/api\/useful-links\/(\d+)$/)
    if (method === 'PUT' && match) {
      const body = JSON.parse(String(init?.body)) as Pick<UsefulLink, 'title' | 'category' | 'url' | 'description'>
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

  it('keeps card actions at accessible 44px targets', () => {
    expect(PAGE_CSS).toMatch(
      /\.useful-open-link\s*\{[^}]*min-height:\s*44px;/s,
    )
    expect(PAGE_CSS).toMatch(
      /\.useful-card-actions button\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px;/s,
    )
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

  it('показывает вкладки со счётчиками и фильтрует выбранную категорию локально', async () => {
    const user = userEvent.setup()
    const fetchMock = createUsefulFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<UsefulThingsPage />)
    await screen.findByText('Figma')

    expect(screen.getByRole('button', { name: 'Все, 4' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Промпты, 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сайты, 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Магазины, 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Статьи, 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Другое, 0' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Промпты, 1' }))

    expect(screen.getByRole('button', { name: 'Промпты, 1' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Аудит лендинга')).toBeInTheDocument()
    expect(screen.queryByText('Figma')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await user.type(screen.getByLabelText('Поиск по полезным вещам'), 'точки роста')
    expect(screen.getByText('Аудит лендинга')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('фильтрует каталог локально по описанию', async () => {
    const user = userEvent.setup()
    const fetchMock = createUsefulFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<UsefulThingsPage />)
    await screen.findByText('Figma')

    await user.type(screen.getByLabelText('Поиск по полезным вещам'), 'документация')

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
      category: 'website',
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
      category: 'website',
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

  it('добавляет промпт без адреса из активной вкладки', async () => {
    const user = userEvent.setup()
    const fetchMock = createUsefulFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<UsefulThingsPage />)
    await screen.findByText('Figma')

    await user.click(screen.getByRole('button', { name: 'Промпты, 1' }))
    await user.click(screen.getByRole('button', { name: 'Добавить промпт' }))
    const dialog = screen.getByRole('dialog', { name: 'Добавить промпт' })

    expect(within(dialog).getByLabelText('Категория')).toHaveValue('prompt')
    expect(within(dialog).queryByLabelText('Адрес сайта')).not.toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('Название'), 'Сильный оффер')
    await user.type(within(dialog).getByLabelText('Текст промпта'), 'Сформулируй три сильных оффера.')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить промпт' }))

    expect(await screen.findByText('Сильный оффер')).toBeInTheDocument()
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      title: 'Сильный оффер',
      category: 'prompt',
      url: '',
      description: 'Сформулируй три сильных оффера.',
    })
  })

  it('копирует полный текст промпта и сообщает об успехе', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    vi.stubGlobal('fetch', createUsefulFetch())
    render(<UsefulThingsPage />)
    await screen.findByText('Аудит лендинга')

    await user.click(screen.getByRole('button', { name: 'Копировать Аудит лендинга' }))

    expect(writeText).toHaveBeenCalledWith('Проанализируй первый экран лендинга и найди точки роста.')
    expect(await screen.findByRole('status')).toHaveTextContent('Промпт скопирован')
  })

  it('показывает доступную ошибку, если буфер обмена недоступен', async () => {
    const user = userEvent.setup()
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('Буфер обмена недоступен'))
    vi.stubGlobal('fetch', createUsefulFetch())
    render(<UsefulThingsPage />)
    await screen.findByText('Аудит лендинга')

    await user.click(screen.getByRole('button', { name: 'Копировать Аудит лендинга' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Буфер обмена недоступен')
  })
})
