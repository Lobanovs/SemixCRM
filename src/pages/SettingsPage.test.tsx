import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SettingsPage from './SettingsPage'


const SETTINGS = {
  enabled: true,
  api_key_configured: true,
  api_key_hint: '••••1234',
  api_key_source: 'database',
  model: 'deepseek-v4-flash',
  base_url: 'https://opencode.ai/zen/go/v1',
  timeout: 45,
  updated_at: '2026-07-27T10:00:00+00:00',
  supported_models: [
    { id: 'gpt-5.6-luna', label: 'GPT-5.6 Luna' },
    { id: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
    { id: 'glm-5.2', label: 'GLM-5.2' },
  ],
}

const PROFILE = {
  name: 'Семён',
  role: 'Разрабатываю сайты для бизнеса',
  stack: 'React, TypeScript, Python',
  portfolio_url: 'https://semyon-lobanov-portfolio.vercel.app/',
  price_from: 'от 50 000 ₽',
  cases: 'Сайты клиник и салонов',
  offer: 'Показываю, как упростить онлайн-запись',
  tone: 'Коротко, уважительно, без давления',
  signature: 'Семён',
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function createSettingsFetch(options: {
  enabled?: boolean
  failSave?: string
  failTest?: string
  failProfileSave?: string
} = {}) {
  const initial = options.enabled === false
    ? { ...SETTINGS, enabled: false, api_key_configured: false, api_key_hint: '', api_key_source: '' }
    : SETTINGS
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'
    if (method === 'GET' && url.endsWith('/api/ai/settings')) return jsonResponse(initial)
    if (method === 'GET' && url.endsWith('/api/ai/profile')) return jsonResponse(PROFILE)
    if (method === 'PUT' && url.endsWith('/api/ai/profile')) {
      if (options.failProfileSave) return jsonResponse({ detail: options.failProfileSave }, 422)
      return jsonResponse(JSON.parse(String(init?.body)))
    }
    if (method === 'PUT' && url.endsWith('/api/ai/settings')) {
      if (options.failSave) return jsonResponse({ detail: options.failSave }, 422)
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>
      return jsonResponse({
        ...SETTINGS,
        enabled: true,
        api_key_configured: true,
        api_key_hint: typeof body.api_key === 'string' ? '••••-key' : SETTINGS.api_key_hint,
        model: body.model,
        timeout: body.timeout,
      })
    }
    if (method === 'POST' && url.endsWith('/api/ai/settings/test')) {
      if (options.failTest) return jsonResponse({ detail: options.failTest }, 502)
      return jsonResponse({ ok: true, message: 'Подключение работает', model: 'deepseek-v4-flash' })
    }
    if (method === 'DELETE' && url.endsWith('/api/ai/settings/key')) {
      return jsonResponse({
        ok: true,
        removed: true,
        settings: { ...SETTINGS, enabled: false, api_key_configured: false, api_key_hint: '', api_key_source: '' },
      })
    }
    throw new Error(`Unexpected request: ${method} ${url}`)
  })
}

describe('настройки OpenCode Go', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('loads the masked connection state without putting the saved key in the input', async () => {
    vi.stubGlobal('fetch', createSettingsFetch())

    render(<SettingsPage />)

    expect(await screen.findByText('OpenCode Go подключён')).toBeInTheDocument()
    expect(screen.getByText('••••1234')).toBeInTheDocument()
    expect(screen.getByLabelText('API-ключ OpenCode Go')).toHaveValue('')
    expect(screen.queryByDisplayValue('go-secret-1234')).not.toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'GPT-5.6 Luna' })).toHaveValue('gpt-5.6-luna')
    expect(screen.getByText('Доступные модели OpenCode, проверенные с текущим API Semix CRM.')).toBeInTheDocument()
  })

  it('saves a replacement key and selected model', async () => {
    const user = userEvent.setup()
    const fetchMock = createSettingsFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<SettingsPage />)
    await screen.findByText('OpenCode Go подключён')

    await user.type(screen.getByLabelText('API-ключ OpenCode Go'), 'new-secret-key')
    await user.selectOptions(screen.getByLabelText('Модель'), 'glm-5.2')
    await user.click(screen.getByRole('button', { name: 'Сохранить настройки' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Настройки сохранены'))
    const saveCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(String(saveCall?.[1]?.body))).toEqual({
      api_key: 'new-secret-key',
      model: 'glm-5.2',
      timeout: 45,
    })
    expect((saveCall?.[1]?.headers as Record<string, string>)['X-Requested-With']).toBe('SemixCRM')
    expect(screen.getByLabelText('API-ключ OpenCode Go')).toHaveValue('')
  })

  it('preserves the existing key when the key input is empty', async () => {
    const user = userEvent.setup()
    const fetchMock = createSettingsFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<SettingsPage />)
    await screen.findByText('OpenCode Go подключён')

    await user.selectOptions(screen.getByLabelText('Модель'), 'glm-5.2')
    await user.click(screen.getByRole('button', { name: 'Сохранить настройки' }))

    const saveCall = await waitFor(() => fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT'))
    expect(JSON.parse(String(saveCall?.[1]?.body))).toEqual({ model: 'glm-5.2', timeout: 45 })
  })

  it('tests an unsaved key and reports success', async () => {
    const user = userEvent.setup()
    const fetchMock = createSettingsFetch({ enabled: false })
    vi.stubGlobal('fetch', fetchMock)
    render(<SettingsPage />)

    await user.type(await screen.findByLabelText('API-ключ OpenCode Go'), 'temporary-key')
    await user.click(screen.getByRole('button', { name: 'Проверить подключение' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Подключение работает')
    const testCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(testCall?.[1]?.body))).toMatchObject({ api_key: 'temporary-key' })
  })

  it('can show and hide the entered key', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createSettingsFetch({ enabled: false }))
    render(<SettingsPage />)

    const input = await screen.findByLabelText('API-ключ OpenCode Go')
    expect(input).toHaveAttribute('type', 'password')
    await user.click(screen.getByRole('button', { name: 'Показать API-ключ' }))
    expect(input).toHaveAttribute('type', 'text')
    await user.click(screen.getByRole('button', { name: 'Скрыть API-ключ' }))
    expect(input).toHaveAttribute('type', 'password')
  })

  it('requires an explicit second click before removing the key', async () => {
    const user = userEvent.setup()
    const fetchMock = createSettingsFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<SettingsPage />)
    await screen.findByText('OpenCode Go подключён')

    await user.click(screen.getByRole('button', { name: 'Удалить сохранённый ключ' }))
    const confirmation = screen.getByRole('group', { name: 'Подтверждение удаления ключа' })
    expect(within(confirmation).getByText(/генерация сообщений перестанет работать/i)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)

    await user.click(within(confirmation).getByRole('button', { name: 'Да, удалить ключ' }))

    expect(await screen.findByText('OpenCode Go не настроен')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(true)
  })

  it('shows backend errors as an accessible alert', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createSettingsFetch({ failTest: 'Ключ OpenCode отклонён (401)' }))
    render(<SettingsPage />)
    await screen.findByText('OpenCode Go подключён')

    await user.click(screen.getByRole('button', { name: 'Проверить подключение' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Ключ OpenCode отклонён')
  })

  it('loads the working profile used for AI generations', async () => {
    vi.stubGlobal('fetch', createSettingsFetch())

    render(<SettingsPage />)

    expect(await screen.findByRole('heading', { name: 'Рабочий AI-профиль' })).toBeInTheDocument()
    expect(screen.getByLabelText('Ваше имя')).toHaveValue('Семён')
    expect(screen.getByLabelText('Ссылка на портфолио')).toHaveValue(PROFILE.portfolio_url)
    expect(screen.getByLabelText('Тон сообщений')).toHaveValue(PROFILE.tone)
  })

  it('saves the working profile and sends the mutation safety header', async () => {
    const user = userEvent.setup()
    const fetchMock = createSettingsFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<SettingsPage />)

    const nameInput = await screen.findByLabelText('Ваше имя')
    await user.clear(nameInput)
    await user.type(nameInput, 'Семён Лобанов')
    await user.clear(screen.getByLabelText('Цена от'))
    await user.type(screen.getByLabelText('Цена от'), 'от 75 000 ₽')
    await user.click(screen.getByRole('button', { name: 'Сохранить AI-профиль' }))

    expect(await screen.findByText(/^Рабочий профиль сохранён/)).toBeInTheDocument()
    const saveCall = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith('/api/ai/profile') && init?.method === 'PUT')
    expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({ name: 'Семён Лобанов', price_from: 'от 75 000 ₽' })
    expect((saveCall?.[1]?.headers as Record<string, string>)['X-Requested-With']).toBe('SemixCRM')
  })

  it('shows profile saving errors next to the profile form', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', createSettingsFetch({ failProfileSave: 'Не удалось сохранить профиль' }))
    render(<SettingsPage />)

    await user.click(await screen.findByRole('button', { name: 'Сохранить AI-профиль' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось сохранить профиль')
  })
})
