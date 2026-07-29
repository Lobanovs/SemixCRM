import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ClientMessageModal from './ClientMessageModal'

const clientMessageModalCss = readFileSync(resolve('src/pages/ClientMessageModal.css'), 'utf8')

const GENERATED = {
  ready: true,
  cached: false,
  model: 'test-model',
  portfolio_url: 'https://semyon-lobanov-portfolio.vercel.app/',
  analysis: 'Рейтинг 5,0 и 200 отзывов. Неясно, как пациенты узнают цены и записываются.',
  pain: 'Нужно уточнить текущий процесс',
  money_argument: 'Ответ владельца покажет, есть ли разрыв.',
  insights: {
    signal: 'Рейтинг 5,0 и 200 отзывов',
    problem: 'Неясно, как пациенты узнают цены и записываются',
    opportunity: 'Ответ владельца поможет продолжить диагностику',
  },
  variants: [
    { tone: 'confident', title: 'Цены и информация', angle: 'Цены и информация', text: 'Здравствуйте! В карточке 2GIS не увидел отдельного сайта с услугами и ценами. Клиенты уточняют стоимость у администратора или есть отдельный прайс?' },
    { tone: 'hard_sell', title: 'Запись и заявки', angle: 'Запись и заявки', text: 'Здравствуйте! В карточке вижу телефон и Telegram, но не вижу онлайн-записи. Клиенты записываются сообщением администратору или через другую систему?' },
    { tone: 'expert', title: 'Обработка обращений', angle: 'Обработка обращений', text: 'Здравствуйте! У 7R высокий рейтинг и 200 отзывов. Кто отвечает пациентам, если они пишут вечером или администратор занят?' },
  ],
  follow_up: '',
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

function renderModal(onSent = vi.fn(), onGenerated = vi.fn()) {
  render(<ClientMessageModal clientId={28} clientName="7R" enabled onClose={vi.fn()} onSent={onSent} onGenerated={onGenerated} />)
  return onSent
}

describe('диалог первого сообщения клиенту', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('показывает три компактных вывода вместо полотна анализа', async () => {
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Сильный сигнал')).toBeInTheDocument()
    expect(within(dialog).getByText('Гипотеза')).toBeInTheDocument()
    expect(within(dialog).getByText('Возможность')).toBeInTheDocument()
    expect(within(dialog).getByText('Рейтинг 5,0 и 200 отзывов')).toBeInTheDocument()
  })

  it('не запускает платную генерацию при простом открытии пустого диалога', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    renderModal()

    expect(await screen.findByRole('button', { name: 'Сгенерировать 3 вопроса' })).toBeVisible()
    expect(screen.getByLabelText('Наблюдение о клиенте (необязательно)')).toBeVisible()
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })

  it('генерирует тексты только по явной кнопке и передаёт ручное наблюдение', async () => {
    const user = userEvent.setup()
    const onGenerated = vi.fn()
    vi.stubGlobal('fetch', createFetchMock())
    renderModal(vi.fn(), onGenerated)

    const observation = await screen.findByLabelText('Наблюдение о клиенте (необязательно)')
    await user.type(observation, 'Клиенты хвалят мастера Анну')
    await user.click(screen.getByRole('button', { name: 'Сгенерировать 3 вопроса' }))

    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')
      expect(call).toBeDefined()
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        manual_observation: 'Клиенты хвалят мастера Анну',
      })
    })
    expect(await screen.findByRole('tab', { name: /Цены и информация/ })).toBeInTheDocument()
    expect(onGenerated).toHaveBeenCalled()
  })

  it('не добавляет портфолио в первое диагностическое сообщение', async () => {
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    const editor = await screen.findByLabelText('Первый диагностический вопрос')
    expect((editor as HTMLTextAreaElement).value).not.toContain('http')
    expect(screen.queryByRole('checkbox', { name: 'Добавлять портфолио в тексты' })).not.toBeInTheDocument()
  })

  it('даёт три диагностических угла и выбирает цены первой', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getAllByRole('tab')).toHaveLength(3)
    expect(within(dialog).getByRole('tab', { name: /Цены и информация/ })).toHaveAttribute('aria-selected', 'true')
    expect(within(dialog).getByRole('tab', { name: /Запись и заявки/ })).toBeInTheDocument()
    expect(within(dialog).getByRole('tab', { name: /Обработка обращений/ })).toBeInTheDocument()
    expect((screen.getByLabelText('Первый диагностический вопрос') as HTMLTextAreaElement).value).toContain('отдельный прайс')

    await user.click(within(dialog).getByRole('tab', { name: /Обработка обращений/ }))

    expect((screen.getByLabelText('Первый диагностический вопрос') as HTMLTextAreaElement).value).toContain('пишут вечером')
  })

  it('подставляет текст выбранного варианта в ссылку WhatsApp', async () => {
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    const link = await screen.findByRole('link', { name: /Открыть WhatsApp/ })
    expect(link).toHaveAttribute('href', expect.stringContaining('https://wa.me/79636775777?text='))
    expect(link.getAttribute('href')).toContain(encodeURIComponent('отдельный прайс'))
  })

  it('сохраняет отдельный черновик каждой стратегии и меняет ссылку отправки', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    const textarea = await screen.findByLabelText('Первый диагностический вопрос')
    await user.clear(textarea)
    await user.type(textarea, 'Свой уверенный текст')

    expect(screen.getByRole('link', { name: /Открыть WhatsApp/ }).getAttribute('href'))
      .toContain(encodeURIComponent('Свой уверенный текст'))

    await user.click(screen.getByRole('tab', { name: /Обработка обращений/ }))
    await user.clear(textarea)
    await user.type(textarea, 'Свой экспертный текст')
    await user.click(screen.getByRole('tab', { name: /Цены и информация/ }))

    expect(textarea).toHaveValue('Свой уверенный текст')
    await user.click(screen.getByRole('tab', { name: /Обработка обращений/ }))
    expect(textarea).toHaveValue('Свой экспертный текст')
  })

  it('переход в мессенджер отмечает клиента как «Написал»', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
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

  it('кнопка «Переписать 3 вопроса» запрашивает новую генерацию', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    await user.click(await screen.findByRole('button', { name: /Переписать 3 вопроса/ }))

    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'POST' && String(url).includes('force=true'))
      expect(call).toBeDefined()
      expect((call?.[1]?.headers as Record<string, string>)['X-Requested-With']).toBe('SemixCRM')
    })
  })

  it('ошибку модели показывает текстом, а не пустым окном', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ failGenerate: 'Лимит запросов исчерпан (429)' }))
    renderModal()

    await user.click(await screen.findByRole('button', { name: 'Сгенерировать 3 вопроса' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Лимит запросов исчерпан')
  })

  it('после ошибки предлагает повторить генерацию', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ failGenerateOnce: 'Модель вернула ответ без JSON' }))
    renderModal()

    const generate = await screen.findByRole('button', { name: 'Сгенерировать 3 вопроса' })
    await user.click(generate)
    expect(await screen.findByRole('alert')).toHaveTextContent('Модель вернула ответ без JSON')
    await user.click(generate)

    expect(await screen.findByRole('tab', { name: /Цены и информация/ })).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2)
  })

  it('показывает карту следующих этапов разговора', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    await user.click(await screen.findByText('Что делать после ответа'))
    expect(screen.getByText('Найти слабое место')).toBeVisible()
    expect(screen.getByText('Показать решение')).toBeVisible()
    expect(screen.getByText('Предложить следующий шаг')).toBeVisible()
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

  it('сохраняет широкий grid-макет поверх общих стилей компактной модалки', async () => {
    vi.stubGlobal('fetch', createFetchMock({ cached: true }))
    renderModal()

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveClass('compact-modal', 'client-message-modal')
    expect(clientMessageModalCss).toMatch(/\.compact-modal\.client-message-modal\s*\{[^}]*display:\s*grid;/s)
    expect(clientMessageModalCss).toMatch(/\.compact-modal\.client-message-modal\s*\{[^}]*overflow:\s*hidden;/s)
  })

  it('без ключа объясняет, как включить, и не дёргает модель', async () => {
    const fetchMock = createFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    render(<ClientMessageModal clientId={28} clientName="7R" enabled={false} onClose={vi.fn()} onSent={vi.fn()} />)

    expect(await screen.findByText('Как включить')).toBeInTheDocument()
    expect(screen.getByText(/Откройте раздел «Настройки»/)).toBeInTheDocument()
    expect(screen.queryByText(/OPENCODE_API_KEY/)).not.toBeInTheDocument()
    // Главное: пустое окно с ошибкой заменено на инструкцию, запросов при этом нет.
    expect(screen.queryByLabelText('Первый диагностический вопрос')).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
