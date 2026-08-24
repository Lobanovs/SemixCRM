import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ActionCenter from './ActionCenter'


const dashboardPayload = {
  generated_at: '2026-08-24T10:00:00+00:00',
  stats: { clients_total: 1216, clients_to_contact: 18, tasks_open: 3, jobs_new: 9, freelance_active: 4 },
  clients: [{ id: 7, name: 'ЕвроДент', niche: 'Стоматология', city: 'Москва', score: 82, score_max: 100, rating: 4.9, reviews: 229, phone: '+79990000000' }],
  tasks: [{ id: 3, title: 'Написать пяти клиентам', date: '2026-08-24', time: '11:00', kind: 'task' }],
  jobs: [{ id: 5, role: 'Frontend developer', company: 'Acme', source: 'habr', relevance: 88, salary_text: '200 000 ₽', discovered_at: '2026-08-24T08:00:00+00:00' }],
  freelance: [{ id: 9, title: 'Сделать сайт клиники', source: 'kwork', relevance: 91, budget_text: '80 000 ₽', published_at: '2026-08-24T08:00:00+00:00' }],
  source_health: [
    { kind: 'freelance', source: 'youdo', status: 'error', state: 'error', checked_at: '2026-08-24T09:00:00+00:00', error: 'Нужно войти', is_stale: false, needs_attention: true },
    { kind: 'jobs', source: 'habr', status: 'done', state: 'healthy', checked_at: '2026-08-24T09:00:00+00:00', error: '', is_stale: false, needs_attention: false },
  ],
}

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('ActionCenter', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('shows the daily queues and opens their source sections', async () => {
    const onOpen = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async () => response(dashboardPayload)))
    render(<ActionCenter onOpen={onOpen} />)

    expect(await screen.findByRole('heading', { name: 'Что важно сегодня' })).toBeInTheDocument()
    expect(screen.getByText('ЕвроДент')).toBeInTheDocument()
    expect(screen.getByText('Написать пяти клиентам')).toBeInTheDocument()
    expect(screen.getByText('Frontend developer')).toBeInTheDocument()
    expect(screen.getByText('Сделать сайт клиники')).toBeInTheDocument()
    expect(screen.getByText('YouDo требует внимания')).toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: 'Открыть клиентов' }))
    expect(onOpen).toHaveBeenCalledWith('clients')
  })

  it('keeps navigation usable and retries after a dashboard error', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ detail: 'Backend недоступен' }, 500))
      .mockResolvedValueOnce(response(dashboardPayload))
    vi.stubGlobal('fetch', fetchMock)
    render(<ActionCenter onOpen={vi.fn()} />)

    expect(await screen.findByText('Backend недоступен')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Повторить загрузку' }))

    await waitFor(() => expect(screen.getByText('ЕвроДент')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
