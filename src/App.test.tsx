import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'


function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function createAppFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/dashboard')) return jsonResponse({
      stats: { clients_total: 0, clients_to_contact: 0, tasks_open: 0, jobs_new: 0, freelance_active: 0 },
      clients: [], tasks: [], jobs: [], freelance: [], source_health: [],
    })
    if (url.endsWith('/api/projects')) return jsonResponse({ stats: { total: 0 } })
    if (url.endsWith('/api/jobs')) return jsonResponse({ stats: { total: 0 } })
    if (url.endsWith('/api/clients')) return jsonResponse({ stats: { total: 0 } })
    if (url.endsWith('/api/schedule')) return jsonResponse({ stats: { total: 0, done: 0 } })
    if (url.endsWith('/api/useful-links')) return jsonResponse({ items: [], stats: { total: 0 } })
    if (url.endsWith('/api/ai/settings')) {
      return jsonResponse({
        enabled: false,
        api_key_configured: false,
        api_key_hint: '',
        api_key_source: '',
        model: 'deepseek-v4-flash',
        base_url: 'https://opencode.ai/zen/go/v1',
        timeout: 90,
        updated_at: '',
        supported_models: [{ id: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' }],
      })
    }
    throw new Error(`Unexpected request: ${url}`)
  })
}

describe('навигация приложения', () => {
  beforeEach(() => vi.stubGlobal('scrollTo', vi.fn()))

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    window.localStorage.clear()
    window.history.replaceState(null, '', window.location.pathname)
  })

  it('scrolls the workspace only after the selected section has rendered', async () => {
    vi.stubGlobal('fetch', createAppFetch())
    let headingWasRendered = false
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      configurable: true,
      value: vi.fn(() => {
        headingWasRendered = screen.queryByRole('heading', { name: 'Настройки', level: 1 }) !== null
      }),
    })
    render(<App />)

    await userEvent.setup().click(screen.getByRole('button', { name: 'Настройки' }))

    expect(await screen.findByRole('heading', { name: 'Настройки', level: 1 })).toBeInTheDocument()
    expect(headingWasRendered).toBe(true)
  })

  it('opens the useful things catalog from the sidebar', async () => {
    vi.stubGlobal('fetch', createAppFetch())
    render(<App />)

    expect(
      screen.getByRole('button', { name: /Полезные вещи\s*Промпты, сайты и статьи/ }),
    ).toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: 'Полезные вещи' }))

    expect(await screen.findByRole('heading', { name: 'Полезные вещи', level: 1 })).toBeInTheDocument()
  })

  it('activates and persists the premium dark theme', async () => {
    vi.stubGlobal('fetch', createAppFetch())
    const { container } = render(<App />)
    const shell = container.querySelector('.app-shell')

    expect(shell).not.toHaveAttribute('data-theme')

    await userEvent.setup().click(screen.getByRole('button', { name: 'Включить тёмную тему' }))

    expect(shell).toHaveClass('theme-dark')
    expect(shell).toHaveAttribute('data-theme', 'premium-dark')
    expect(window.localStorage.getItem('semix-crm-theme')).toBe('dark')
  })

  it('opens a section from the URL hash and follows browser navigation', async () => {
    vi.stubGlobal('fetch', createAppFetch())
    window.history.replaceState(null, '', '#clients')
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Волк с Уолл-стрит', level: 1 })).toBeInTheDocument()

    window.history.pushState(null, '', '#schedule')
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    expect(await screen.findByRole('heading', { name: 'Расписание по дням', level: 1 })).toBeInTheDocument()
  })

  it('opens working profile settings from the header', async () => {
    vi.stubGlobal('fetch', createAppFetch())
    render(<App />)

    await userEvent.setup().click(screen.getByRole('button', { name: 'Открыть рабочий профиль' }))

    expect(await screen.findByRole('heading', { name: 'Настройки', level: 1 })).toBeInTheDocument()
    expect(window.location.hash).toBe('#settings')
  })
})
