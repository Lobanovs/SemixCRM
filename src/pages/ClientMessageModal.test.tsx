import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ClientMessageModal from './ClientMessageModal'

const GENERATED = {
  ready: true,
  cached: false,
  model: 'test-model',
  analysis: 'Рейтинг 5,0 и 200 отзывов. В карточке не указан сайт. Можно упростить путь до обращения.',
  pain: 'В карточке не указан полноценный сайт',
  money_argument: 'Даже одно дополнительное обращение может окупить улучшение.',
  insights: {
    signal: 'Рейтинг 5,0 и 200 отзывов',
    problem: 'В карточке не указан полноценный сайт',
    opportunity: 'Упростить путь до обращения',
  },
  variants: [
    { tone: 'confident', title: 'Уверенный продавец', angle: 'Уверенный продавец', text: 'Добрый день! У «7R» рейтинг 5,0 и 200 отзывов — доверие уже заработано. В карточке не вижу полноценного сайта, только Telegram. Могу прислать короткий разбор с тремя точками роста — куда удобнее отправить? Семён' },
    { tone: 'hard_sell', title: 'Жёсткая продажа', angle: 'Жёсткая продажа', text: 'Добрый день! 200 отзывов приводят внимание к «7R», но без сайта часть этого спроса негде превращать в записи. Даже одно обращение может окупить улучшение. Покажу, где обрывается путь до заявки — прислать сюда? Семён' },
    { tone: 'expert', title: 'Эксперт', angle: 'Эксперт', text: 'Здравствуйте! Посмотрел путь пациента у «7R»: карточка сильная — 5,0 и 200 отзывов, но следующим шагом вижу только Telegram. Могу бесплатно показать прототип первого экрана под вашу клинику — посмотреть? Семён' },
  ],
  follow_up: 'Добрый день! Разбор всё ещё в силе, если интересно.',
  warnings: [],
  links: [
    { channel: 'WhatsApp', url: 'https://wa.me/79636775777' },
    { channel: 'Telegram', url: 'https://t.me/stom7r' },
  ],
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

function createFetchMock(options: {
  cached?: boolean
  failGenerate?: string
  failGenerateOnce?: string
  payload?: typeof GENERATED | Record<string, unknown>
} = {}) {
  let postCount = 0
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'
    if (method === 'GET' && url.includes('/api/ai/clients/28/message')) {
      return jsonResponse(options.cached ? { ...(options.payload ?? GENERATED), cached: true } : { ready: false })
    }
    if (method === 'POST' && url.includes('/api/ai/clients/28/message')) {
      postCount += 1
      if (options.failGenerate) return jsonResponse({ detail: options.failGenerate }, 502)
      if (options.failGenerateOnce && postCount === 1) {
        return jsonResponse({ detail: options.failGenerateOnce }, 502)
      }
      return jsonResponse(options.payload ?? GENERATED)
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

  it('показывает три компактных вывода вместо полотна анализа', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Сильный сигнал')).toBeInTheDocument()
    expect(within(dialog).getByText('Гипотеза')).toBeInTheDocument()
    expect(within(dialog).getByText('Возможность')).toBeInTheDocument()
    expect(within(dialog).getByText('Рейтинг 5,0 и 200 отзывов')).toBeInTheDocument()
  })

  it('даёт три стратегии и выбирает уверенного продавца первой', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getAllByRole('tab')).toHaveLength(3)
    expect(within(dialog).getByRole('tab', { name: /Уверенный продавец/ })).toHaveAttribute('aria-selected', 'true')
    expect(within(dialog).getByRole('tab', { name: /Жёсткая продажа/ })).toBeInTheDocument()
    expect(within(dialog).getByRole('tab', { name: /Эксперт/ })).toBeInTheDocument()
    expect((screen.getByLabelText('Текст сообщения') as HTMLTextAreaElement).value).toContain('доверие уже заработано')

    await user.click(within(dialog).getByRole('tab', { name: /Эксперт/ }))

    expect((screen.getByLabelText('Текст сообщения') as HTMLTextAreaElement).value).toContain('Посмотрел путь пациента')
  })

  it('подставляет текст выбранного варианта в ссылку WhatsApp', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    const link = await screen.findByRole('link', { name: /Открыть WhatsApp/ })
    expect(link).toHaveAttribute('href', expect.stringContaining('https://wa.me/79636775777?text='))
    expect(link.getAttribute('href')).toContain(encodeURIComponent('доверие уже заработано'))
  })

  it('сохраняет отдельный черновик каждой стратегии и меняет ссылку отправки', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    const textarea = await screen.findByLabelText('Текст сообщения')
    await user.clear(textarea)
    await user.type(textarea, 'Свой уверенный текст')

    expect(screen.getByRole('link', { name: /Открыть WhatsApp/ }).getAttribute('href'))
      .toContain(encodeURIComponent('Свой уверенный текст'))

    await user.click(screen.getByRole('tab', { name: /Эксперт/ }))
    await user.clear(textarea)
    await user.type(textarea, 'Свой экспертный текст')
    await user.click(screen.getByRole('tab', { name: /Уверенный продавец/ }))

    expect(textarea).toHaveValue('Свой уверенный текст')
    await user.click(screen.getByRole('tab', { name: /Эксперт/ }))
    expect(textarea).toHaveValue('Свой экспертный текст')
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

    await screen.findByText('Рейтинг 5,0 и 200 отзывов')

    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
    expect(screen.getByText('Сохранённый результат')).toBeInTheDocument()
  })

  it('кнопка «Переписать заново» запрашивает новую генерацию', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    await user.click(await screen.findByRole('button', { name: /Переписать 3 варианта/ }))

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

  it('после ошибки предлагает повторить генерацию', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ failGenerateOnce: 'Модель вернула ответ без JSON' }))
    renderModal()

    await user.click(await screen.findByRole('button', { name: 'Повторить' }))

    expect(await screen.findByRole('tab', { name: /Уверенный продавец/ })).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2)
  })

  it('показывает напоминание на случай молчания', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    expect(await screen.findByText(/Разбор всё ещё в силе/)).toBeInTheDocument()
  })

  it('поддерживает сохранённые варианты старого формата', async () => {
    const legacy = {
      ...GENERATED,
      insights: undefined,
      variants: [
        { angle: 'Наблюдение', text: GENERATED.variants[0].text },
        { angle: 'Деньги', text: GENERATED.variants[1].text },
        { angle: 'Короткий', text: GENERATED.variants[2].text },
      ],
    }
    vi.stubGlobal('fetch', createFetchMock({ cached: true, payload: legacy }))
    renderModal()

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getAllByRole('tab')).toHaveLength(3)
    expect(within(dialog).getByRole('tab', { name: /^Наблюдение/ })).toBeInTheDocument()
    expect(within(dialog).getByText('Сильный сигнал')).toBeInTheDocument()
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
