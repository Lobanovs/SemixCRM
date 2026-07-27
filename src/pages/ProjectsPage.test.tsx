import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ProjectsPage from './ProjectsPage'

const project = {
  id: 1,
  name: 'Личный сайт',
  description: 'Портфолио с блогом',
  path: 'C:\\sites\\portfolio',
  command: 'npm run dev',
  url: '',
  port: 5173,
  tags: ['Next.js'],
  category: 'Веб-сайт',
  status: 'В работе',
  version: '1.2.0',
  repo_url: '',
  progress: 65,
  last_started_at: '',
  run_count: 0,
  archived: false,
  created_at: '2026-07-26T09:00:00+00:00',
  updated_at: '2026-07-26T09:00:00+00:00',
}

const stoppedRuntime = {
  project_id: 1, status: 'stopped', pid: null, started_at: '', url: '', port: 5173, exit_code: null, last_line: '',
}

const runningRuntime = {
  project_id: 1, status: 'running', pid: 4242, started_at: '2026-07-26T10:00:00+00:00',
  url: 'http://localhost:5173/', port: 5173, exit_code: null, last_line: 'ready in 320 ms',
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

function createFetchMock(options: { running?: boolean } = {}) {
  const runtime = options.running ? runningRuntime : stoppedRuntime
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'

    if (method === 'GET' && url.includes('/api/projects/1/logs')) {
      return jsonResponse({ project_id: 1, runtime, logs: ['vite v8.1.5 dev server running'] })
    }
    if (method === 'GET' && url.includes('/api/projects')) {
      return jsonResponse({
        projects: [project],
        stats: { total: 1, active: 1, in_progress: 1, done: 0, paused: 0, started_today: 0 },
        runtime: { '1': runtime },
        categories: ['Веб-приложение', 'Веб-сайт'],
        statuses: ['В работе', 'Готов', 'Пауза'],
      })
    }
    if (method === 'POST' && url.endsWith('/api/projects/detect')) {
      return jsonResponse({
        name: 'portfolio', description: 'Сайт-портфолио', command: 'npm run dev', port: 4300,
        version: '2.0.0', category: 'Веб-приложение', tags: ['Vite'], scripts: ['dev'], exists: true, kind: 'node',
      })
    }
    if (method === 'POST' && url.endsWith('/api/projects/1/start')) return jsonResponse({ ok: true, runtime: runningRuntime })
    if (method === 'POST' && url.endsWith('/api/projects/1/stop')) return jsonResponse({ ok: true, runtime: stoppedRuntime })
    if (method === 'POST' && url.endsWith('/api/projects/start-all')) {
      return jsonResponse({
        started: [{ id: 1, name: 'Личный сайт', port: 5173 }],
        skipped: [{ id: 2, name: 'Черновик', reason: 'не задана команда запуска' }],
        failed: [{ id: 3, name: 'Wandor', error: 'Порт 5183 уже занят' }],
      })
    }
    if (method === 'POST' && url.endsWith('/api/projects/stop-all')) return jsonResponse({ stopped_count: 3 })
    if (method === 'POST' && url.endsWith('/api/projects')) return jsonResponse(project, 201)
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
}

describe('страница «Мои проекты»', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('показывает проекты из API, а не демо-данные', async () => {
    vi.stubGlobal('fetch', createFetchMock())
    render(<ProjectsPage />)

    await screen.findByRole('heading', { name: 'Мои проекты', level: 1 })
    // Название встречается и в карточке списка, и в боковой панели выбранного проекта.
    expect(await screen.findAllByRole('heading', { name: 'Личный сайт', level: 2 })).toHaveLength(2)
    expect(screen.getAllByText('npm run dev').length).toBeGreaterThan(0)
    expect(screen.queryByText('Task Manager')).not.toBeInTheDocument()
  })

  it('запускает проект и отправляет защитный заголовок', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    render(<ProjectsPage />)

    // Точное имя: /Запустить/ совпало бы ещё с «Запустить все» и «Запустить проект».
    await user.click((await screen.findAllByRole('button', { name: 'Запустить' }))[0])

    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([url, init]) => init?.method === 'POST' && String(url).endsWith('/api/projects/1/start'))
      expect(call).toBeDefined()
      expect((call?.[1]?.headers as Record<string, string>)['X-Requested-With']).toBe('SemixCRM')
    })
  })

  it('для запущенного проекта предлагает остановку и открытие адреса', async () => {
    vi.stubGlobal('fetch', createFetchMock({ running: true }))
    render(<ProjectsPage />)

    expect(await screen.findAllByRole('button', { name: /Остановить/ })).not.toHaveLength(0)
    expect(screen.getAllByRole('button', { name: /Открыть/ })).not.toHaveLength(0)
    expect(screen.getAllByText('Запущен').length).toBeGreaterThan(0)
  })

  it('показывает лог запущенного проекта', async () => {
    vi.stubGlobal('fetch', createFetchMock({ running: true }))
    render(<ProjectsPage />)

    expect(await screen.findByText(/vite v8.1.5 dev server running/)).toBeInTheDocument()
  })

  it('определяет команду запуска по папке проекта', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    render(<ProjectsPage />)

    await user.click(await screen.findByRole('button', { name: /Добавить проект/ }))
    const dialog = screen.getByRole('heading', { name: 'Новый проект' }).closest('form') as HTMLFormElement

    await user.type(within(dialog).getByLabelText('Папка проекта'), 'C:\\sites\\portfolio')
    await user.click(within(dialog).getByRole('button', { name: /Определить/ }))

    await waitFor(() => {
      expect((within(dialog).getByLabelText('Команда запуска') as HTMLInputElement).value).toBe('npm run dev')
      expect((within(dialog).getByLabelText('Порт (если известен)') as HTMLInputElement).value).toBe('4300')
      expect((within(dialog).getByLabelText('Название') as HTMLInputElement).value).toBe('portfolio')
    })
  })

  it('запускает все проекты одной кнопкой и показывает итог', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<ProjectsPage />)

    await user.click(await screen.findByRole('button', { name: /Запустить все/ }))

    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.some(([url, init]) => init?.method === 'POST' && String(url).endsWith('/api/projects/start-all'))).toBe(true)
    })
    expect(await screen.findByText(/Запущено: 1/)).toBeInTheDocument()
    expect(screen.getByText(/не задана команда запуска/)).toBeInTheDocument()
    expect(screen.getByText(/Порт 5183 уже занят/)).toBeInTheDocument()
  })

  it('не запускает всё, если пользователь отменил подтверждение', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock())
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<ProjectsPage />)

    await user.click(await screen.findByRole('button', { name: /Запустить все/ }))

    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/api/projects/start-all'))).toBe(false)
  })

  it('для запущенных проектов предлагает остановить все', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createFetchMock({ running: true }))
    render(<ProjectsPage />)

    await user.click(await screen.findByRole('button', { name: /Остановить все/ }))

    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.some(([url, init]) => init?.method === 'POST' && String(url).endsWith('/api/projects/stop-all'))).toBe(true)
    })
  })

  it('сообщает об ошибке запуска вместо молчания', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method || 'GET'
      if (method === 'POST' && url.endsWith('/api/projects/1/start')) {
        return jsonResponse({ detail: 'Папка проекта не найдена: C:\\sites\\portfolio' }, 422)
      }
      return createFetchMock()(input, init)
    }))
    render(<ProjectsPage />)

    // Точное имя: /Запустить/ совпало бы ещё с «Запустить все» и «Запустить проект».
    await user.click((await screen.findAllByRole('button', { name: 'Запустить' }))[0])

    expect(await screen.findByRole('alert')).toHaveTextContent('Папка проекта не найдена')
  })
})
