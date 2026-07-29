import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

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
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    window.localStorage.clear()
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
})
