import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ClientMessageModal from './ClientMessageModal'

const GENERATED = {
  ready: true,
  cached: false,
  model: 'test-model',
  analysis: 'Клиника с рейтингом 5,0 и 200 отзывами, но сайта нет — заявки теряются вечером.',
  pain: 'Пациенты находят клинику, но не могут записаться без звонка',
  money_argument: 'Даже два импланта в месяц — это заметные деньги; оценка приблизительная.',
  variants: [
    { angle: 'наблюдение о них', text: 'Добрый день! Посмотрел карточку в 2ГИС: рейтинг 5,0 и двести отзывов. Записаться при этом можно только звонком. Показать короткий разбор? Семён' },
    { angle: 'деньги', text: 'Здравствуйте! У вас двести отзывов, но записаться онлайн негде — часть людей уходит к соседям. Прислать разбор? Семён' },
    { angle: 'короткий', text: 'Добрый день! Нашёл вас в 2ГИС, сайта нет. Сделать бесплатный трёхминутный видеоразбор? Семён' },
  ],
  follow_up: 'Добрый день! Разбор всё ещё в силе, если интересно.',
  warnings: [],
  links: [{ channel: 'WhatsApp', url: 'https://wa.me/79636775777' }],
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

function createFetchMock(options: { cached?: boolean; failGenerate?: string } = {}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'
    if (method === 'GET' && url.includes('/api/ai/clients/28/message')) {
      return jsonResponse(options.cached ? { ...GENERATED, cached: true } : { ready: false })
    }
    if (method === 'POST' && url.includes('/api/ai/clients/28/message')) {
      if (options.failGenerate) return jsonResponse({ detail: options.failGenerate }, 502)
      return jsonResponse(GENERATED)
    }
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
}

function renderModal(onSent = vi.fn()) {
  render(<ClientMessageModal clientId={28} clientName="7R" enabled onClose={vi.fn()} onSent={onSent} />)
  return onSent
}

describe('диалог первого сообщения клиенту', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('показывает разбор карточки, боль и аргумент про деньги', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    expect(await screen.findByText(/рейтингом 5,0 и 200 отзывами/)).toBeInTheDocument()
    expect(screen.getByText(/не могут записаться без звонка/)).toBeInTheDocument()
    expect(screen.getByText(/оценка приблизительная/)).toBeInTheDocument()
  })

  it('даёт три варианта и переключает их', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getAllByRole('tab')).toHaveLength(3)
    expect((screen.getByLabelText('Текст сообщения') as HTMLTextAreaElement).value).toContain('двести отзывов')

    await user.click(within(dialog).getByRole('tab', { name: 'короткий' }))

    expect((screen.getByLabelText('Текст сообщения') as HTMLTextAreaElement).value).toContain('видеоразбор')
  })

  it('подставляет текст выбранного варианта в ссылку WhatsApp', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    const link = await screen.findByRole('link', { name: /Открыть WhatsApp/ })
    expect(link).toHaveAttribute('href', expect.stringContaining('https://wa.me/79636775777?text='))
    expect(link.getAttribute('href')).toContain(encodeURIComponent('двести отзывов'))
  })

  it('редактирование текста меняет ссылку отправки', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    const textarea = await screen.findByLabelText('Текст сообщения')
    await user.clear(textarea)
    await user.type(textarea, 'Свой текст')

    expect(screen.getByRole('link', { name: /Открыть WhatsApp/ }).getAttribute('href'))
      .toContain(encodeURIComponent('Свой текст'))
  })

  it('переход в мессенджер отмечает клиента как «Написал»', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    const onSent = renderModal()

    await user.click(await screen.findByRole('link', { name: /Открыть WhatsApp/ }))

    expect(onSent).toHaveBeenCalled()
  })

  it('сохранённый разбор показывается без обращения к модели', async () => {
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    await screen.findByText(/рейтингом 5,0 и 200 отзывами/)

    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
    expect(screen.getByText('Показан сохранённый разбор')).toBeInTheDocument()
  })

  it('кнопка «Переписать заново» запрашивает новую генерацию', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    await user.click(await screen.findByRole('button', { name: /Переписать заново/ }))

    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'POST' && String(url).includes('force=true'))
      expect(call).toBeDefined()
      expect((call?.[1]?.headers as Record<string, string>)['X-Requested-With']).toBe('SemixCRM')
    })
  })

  it('ошибку модели показывает текстом, а не пустым окном', async () => {
    vi.stubGlobal('fetch', createFetchMock({ failGenerate: 'Лимит запросов исчерпан (429)' }))
    renderModal()

    expect(await screen.findByRole('alert')).toHaveTextContent('Лимит запросов исчерпан')
  })

  it('показывает напоминание на случай молчания', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    expect(await screen.findByText(/Разбор всё ещё в силе/)).toBeInTheDocument()
  })

  it('без ключа объясняет, как включить, и не дёргает модель', async () => {
    const fetchMock = createFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    render(<ClientMessageModal clientId={28} clientName="7R" enabled={false} onClose={vi.fn()} onSent={vi.fn()} />)

    expect(await screen.findByText('Как включить')).toBeInTheDocument()
    expect(screen.getByText(/Откройте раздел «Настройки»/)).toBeInTheDocument()
    expect(screen.queryByText(/OPENCODE_API_KEY/)).not.toBeInTheDocument()
    // Главное: пустое окно с ошибкой заменено на инструкцию, запросов при этом нет.
    expect(screen.queryByLabelText('Текст сообщения')).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
