import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import JobsPage from './JobsPage'

const statuses = ['Сохранено', 'Откликнулся', 'Ответили', 'Собеседование', 'Оффер', 'Отказ']

const job = {
  id: 7,
  source: 'hh',
  external_id: 'hh-121314151',
  company: 'Яндекс',
  role: 'Frontend-разработчик (React)',
  description: 'Разработка интерфейсов сервисов Яндекса.',
  url: 'https://hh.ru/vacancy/121314151',
  tags: ['React', 'TypeScript'],
  salary_min: 200000,
  salary_max: 280000,
  currency: 'RUR',
  salary_text: '200 000 – 280 000 ₽',
  location: 'Москва',
  employment: 'Удаленная работа',
  published_at: '2026-07-25T10:32:00+0300',
  discovered_at: '2026-07-26T08:00:00+00:00',
  relevance: 14,
  relevance_reasons: ['В названии: react'],
  match_score: 70,
  status: 'Сохранено',
  next_step: 'Изучить и откликнуться',
  note: '',
  archived: false,
}

const settings = {
  sources: ['hh', 'habr', 'telegram'],
  keywords: ['react'],
  excluded_keywords: ['стажёр'],
  telegram_channels: ['forfrontend'],
  area: 'Россия',
  salary_min: 150000,
  remote_only: false,
  per_source_limit: 50,
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

function createFetchMock(overrides: { jobs?: unknown[]; keywords?: string[] } = {}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'

    if (method === 'GET' && url.includes('/api/jobs/settings')) {
      return jsonResponse({ ...settings, keywords: overrides.keywords ?? settings.keywords })
    }
    if (method === 'PUT' && url.includes('/api/jobs/settings')) {
      return jsonResponse(JSON.parse(String(init?.body || '{}')))
    }
    if (method === 'GET' && url.includes('/api/jobs/parse/')) {
      return jsonResponse({ run_id: 'r1', status: 'done', message: 'Готово: новых — 4, уже были — 1', error: '', inserted: 4, duplicates: 1, sources: { hh: { status: 'done', found: 5, new: 4 } } })
    }
    if (method === 'POST' && url.includes('/api/jobs/parse')) return jsonResponse({ run_id: 'r1' })
    if (method === 'POST' && url.includes('/api/jobs')) return jsonResponse(job, 201)
    if (method === 'PUT' && url.includes('/api/jobs/')) return jsonResponse({ ...job, status: 'Откликнулся' })
    if (method === 'GET' && url.includes('/api/jobs')) {
      return jsonResponse({
        jobs: overrides.jobs ?? [job],
        stats: { total: 1, found_today: 1, archived: 0, applied: 0, replied: 0, interviews: 0, offers: 0, stages: { Сохранено: 1 }, conversion: 0 },
        sources: [
          { source: 'hh', status: 'done', checked_at: '', found_count: 5, error: '' },
          { source: 'habr', status: 'done', checked_at: '', found_count: 4, error: '' },
          { source: 'telegram', status: 'empty', checked_at: '', found_count: 0, error: '' },
        ],
        statuses,
        available: ['hh', 'habr', 'telegram'],
      })
    }
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
}

describe('страница «Работа (вакансии)»', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('показывает вакансии из API вместо демо-списка', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    render(<JobsPage />)

    expect(await screen.findByRole('heading', { name: 'Яндекс', level: 2 })).toBeInTheDocument()
    expect(screen.getByText('Frontend-разработчик (React)')).toBeInTheDocument()
    expect(screen.getByText('200 000 – 280 000 ₽')).toBeInTheDocument()
    expect(screen.queryByText('Т-Банк')).not.toBeInTheDocument()
  })

  it('перечисляет три поддерживаемых источника', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    render(<JobsPage />)

    await screen.findByRole('heading', { name: 'Парсер вакансий' })
    for (const label of ['hh.ru', 'Хабр Карьера', 'Telegram']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
  })

  it('меняет статус вакансии через API', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    render(<JobsPage />)

    await screen.findByRole('heading', { name: 'Яндекс', level: 2 })
    await user.selectOptions(screen.getByLabelText('Статус вакансии'), 'Откликнулся')

    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'PUT' && String(url).includes('/api/jobs/7'))
      expect(call).toBeDefined()
      expect(JSON.parse(String(call?.[1]?.body)).status).toBe('Откликнулся')
    })
  })

  it('запускает сбор вакансий и показывает итог по источникам', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    render(<JobsPage />)

    await user.click(await screen.findByRole('button', { name: /Запустить парсер/ }))

    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'POST' && String(url).endsWith('/api/jobs/parse'))
      expect(call).toBeDefined()
      expect((call?.[1]?.headers as Record<string, string>)['X-Requested-With']).toBe('SemixCRM')
    })
    // Состояние запуска опрашивается раз в 1,5 секунды — ждём дольше стандартной секунды.
    expect(await screen.findByText(/Готово: новых — 4/, undefined, { timeout: 4000 })).toBeInTheDocument()
  })

  it('предупреждает, когда ключевые слова не заданы', async () => {
    vi.stubGlobal('fetch', createFetchMock({ keywords: [] }))
    render(<JobsPage />)

    expect(await screen.findByText(/нулевая релевантность/)).toBeInTheDocument()
  })

  it('сохраняет настройки парсера с выбранными источниками и каналами', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    render(<JobsPage />)

    await user.click(await screen.findByRole('button', { name: /Настроить/ }))
    const dialog = screen.getByRole('heading', { name: 'Настройки парсера вакансий' }).closest('form') as HTMLFormElement

    // Шесть источников плюс переключатель «только удалённо».
    expect(within(dialog).getAllByRole('checkbox')).toHaveLength(7)
    await user.clear(within(dialog).getByLabelText('Telegram-каналы (без @)'))
    await user.type(within(dialog).getByLabelText('Telegram-каналы (без @)'), 'forfrontend, devjobs')
    await user.click(within(dialog).getByRole('button', { name: /Сохранить настройки/ }))

    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'PUT' && String(url).includes('/api/jobs/settings'))
      expect(call).toBeDefined()
      const body = JSON.parse(String(call?.[1]?.body))
      expect(body.sources).toEqual(['hh', 'habr', 'telegram'])
      expect(body.telegram_channels).toEqual(['forfrontend', 'devjobs'])
    })
  })

  it('показывает пустое состояние без вакансий', async () => {
    vi.stubGlobal('fetch', createFetchMock({ jobs: [] }))
    render(<JobsPage />)

    expect(await screen.findByText(/Вакансий пока нет/)).toBeInTheDocument()
  })

  it('не монтирует все найденные вакансии одновременно', async () => {
    const jobs = Array.from({ length: 51 }, (_, index) => ({
      ...job,
      id: index + 1,
      external_id: `job-${index + 1}`,
      role: `React вакансия ${String(index + 1).padStart(2, '0')}`,
      company: `Компания ${String(index + 1).padStart(2, '0')}`,
    }))
    vi.stubGlobal('fetch', createFetchMock({ jobs }))
    render(<JobsPage />)

    expect(await screen.findByText('Показано 50 из 51')).toBeVisible()
    expect(screen.queryByText('React вакансия 51')).not.toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Показать ещё 1' }))
    expect(screen.getByText('React вакансия 51')).toBeVisible()
  })
})
