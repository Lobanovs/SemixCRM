import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import SchedulePage from './SchedulePage'

type TestTask = {
  id: number
  date: string
  title: string
  time: string
  kind: 'task' | 'meeting'
  done: boolean
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function createScheduleFetch(options: { failTaskUpdates?: boolean } = {}) {
  let tasks: TestTask[] = [{ id: 7, date: '2026-07-22', title: 'Позвонить клиенту', time: '10:00', kind: 'task', done: false }]

  const schedulePayload = () => ({
    week_start: '2026-07-20',
    week_end: '2026-07-26',
    tasks,
    notes: {},
    summary: '',
    goals: [],
    focus: '',
    stats: {
      total: tasks.length,
      done: tasks.filter((task) => task.done).length,
      meetings: tasks.filter((task) => task.kind === 'meeting').length,
      completion_percent: tasks.length ? Math.round((tasks.filter((task) => task.done).length / tasks.length) * 100) : 0,
    },
    upcoming: tasks.filter((task) => !task.done),
    past_weeks: [],
  })

  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'

    if (method === 'GET' && url.includes('/api/schedule?')) return jsonResponse(schedulePayload())
    if (method === 'POST' && url.endsWith('/api/schedule/tasks')) {
      const body = JSON.parse(String(init?.body || '{}'))
      const task: TestTask = { id: 8, date: body.task_date, title: body.title, time: body.task_time, kind: body.kind, done: false }
      tasks = [...tasks, task]
      return jsonResponse(task)
    }
    const taskMatch = url.match(/\/api\/schedule\/tasks\/(\d+)$/)
    if (method === 'PUT' && taskMatch) {
      const body = JSON.parse(String(init?.body || '{}'))
      if (options.failTaskUpdates && 'title' in body) return jsonResponse({ detail: 'Не удалось сохранить задачу' }, 500)
      const taskId = Number(taskMatch[1])
      tasks = tasks.map((task) => task.id === taskId ? {
        ...task,
        ...(body.title !== undefined ? { title: body.title } : {}),
        ...(body.task_date !== undefined ? { date: body.task_date } : {}),
        ...(body.task_time !== undefined ? { time: body.task_time } : {}),
        ...(body.kind !== undefined ? { kind: body.kind } : {}),
        ...(body.done !== undefined ? { done: body.done } : {}),
      } : task)
      return jsonResponse(tasks.find((task) => task.id === taskId))
    }
    if (method === 'DELETE' && taskMatch) {
      const taskId = Number(taskMatch[1])
      tasks = tasks.filter((task) => task.id !== taskId)
      return jsonResponse({ ok: true, deleted_id: taskId })
    }
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
}

describe('schedule task CRUD', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', createScheduleFetch())
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('opens creation for the clicked weekday and saves the task', async () => {
    const user = userEvent.setup()
    render(<SchedulePage />)

    await user.click(await screen.findByRole('button', { name: 'Добавить задачу на Ср 22.07' }))
    const dialog = screen.getByRole('dialog', { name: 'Новая задача' })
    expect(within(dialog).getByLabelText('Дата')).toHaveValue('2026-07-22')

    await user.type(within(dialog).getByLabelText('Название задачи'), 'Новая задача')
    await user.type(within(dialog).getByLabelText('Время'), '13:00')
    await user.click(within(dialog).getByRole('button', { name: 'Добавить задачу' }))

    await waitFor(() => {
      const createCall = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'POST' && String(url).endsWith('/api/schedule/tasks'))
      expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({ title: 'Новая задача', task_date: '2026-07-22', task_time: '13:00', kind: 'task' })
    })
  })

  it('opens an existing task and saves all editable fields', async () => {
    const user = userEvent.setup()
    render(<SchedulePage />)

    await user.click(await screen.findByRole('button', { name: 'Редактировать задачу Позвонить клиенту' }))
    const dialog = screen.getByRole('dialog', { name: 'Редактирование задачи' })
    const title = within(dialog).getByLabelText('Название задачи')
    await user.clear(title)
    await user.type(title, 'Созвон с клиентом')
    await user.clear(within(dialog).getByLabelText('Время'))
    await user.type(within(dialog).getByLabelText('Время'), '15:30')
    await user.selectOptions(within(dialog).getByLabelText('Тип'), 'meeting')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить изменения' }))

    await waitFor(() => {
      const updateCall = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'PUT' && String(url).endsWith('/api/schedule/tasks/7') && String(init.body).includes('Созвон с клиентом'))
      expect(JSON.parse(String(updateCall?.[1]?.body))).toEqual({ title: 'Созвон с клиентом', task_date: '2026-07-22', task_time: '15:30', kind: 'meeting' })
    })
  })

  it('toggles completion without opening the editor', async () => {
    const user = userEvent.setup()
    render(<SchedulePage />)

    await user.click(await screen.findByRole('button', { name: 'Отметить задачу «Позвонить клиенту» выполненной' }))

    await waitFor(() => {
      const completionCall = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'PUT' && String(url).endsWith('/api/schedule/tasks/7'))
      expect(JSON.parse(String(completionCall?.[1]?.body))).toEqual({ done: true })
    })
    expect(screen.queryByRole('dialog', { name: 'Редактирование задачи' })).not.toBeInTheDocument()
  })

  it('requires confirmation before deleting a task', async () => {
    const user = userEvent.setup()
    render(<SchedulePage />)

    await user.click(await screen.findByRole('button', { name: 'Редактировать задачу Позвонить клиенту' }))
    const dialog = screen.getByRole('dialog', { name: 'Редактирование задачи' })
    await user.click(within(dialog).getByRole('button', { name: 'Удалить задачу' }))
    expect(within(dialog).getByText('Удалить задачу без возможности восстановления?')).toBeVisible()
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)

    await user.click(within(dialog).getByRole('button', { name: 'Подтвердить удаление задачи' }))
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => init?.method === 'DELETE' && String(url).endsWith('/api/schedule/tasks/7'))).toBe(true))
  })

  it('keeps the editor open and announces update errors', async () => {
    vi.stubGlobal('fetch', createScheduleFetch({ failTaskUpdates: true }))
    const user = userEvent.setup()
    render(<SchedulePage />)

    await user.click(await screen.findByRole('button', { name: 'Редактировать задачу Позвонить клиенту' }))
    const dialog = screen.getByRole('dialog', { name: 'Редактирование задачи' })
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить изменения' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Не удалось сохранить задачу')
    expect(screen.getByRole('dialog', { name: 'Редактирование задачи' })).toBeVisible()
  })
})
