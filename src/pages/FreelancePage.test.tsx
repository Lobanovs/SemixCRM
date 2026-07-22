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
      return jsonResponse({ orders: [], stats: { total: 0, responded: 0, replied: 0, in_progress: 0, new_today: 0, archived: 0, stages: {} } })
    }
    if (method === 'GET' && url.endsWith('/api/freelance/settings')) return jsonResponse(settings)
    if (method === 'GET' && url.endsWith('/api/freelance/sources')) return jsonResponse({ sources: sourceStatuses })
    if (method === 'GET' && url.endsWith('/api/freelance/sniper/status')) return jsonResponse({ status: 'stopped', sources: {}, interval_seconds: 60 })
    if (method === 'PUT' && url.endsWith('/api/freelance/settings')) return jsonResponse(JSON.parse(String(init?.body || '{}')))
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
})
