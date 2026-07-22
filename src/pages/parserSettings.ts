export type ParserSettings = {
  city: string
  niches: string[]
  sources: string[]
  limit: number
  start_page: number
  updated_at?: string
}

export type ParserStartResult = {
  settings: ParserSettings
  jobId: string
}

type ParserStartOptions = {
  request?: typeof fetch
  onPersist?: (settings: ParserSettings) => void | Promise<void>
}

export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000'

const settingsPayload = (settings: ParserSettings) => ({
  city: settings.city.trim(),
  niches: [...settings.niches],
  sources: [...settings.sources],
  limit: Math.max(1, Math.min(50, Math.round(settings.limit))),
  start_page: Math.max(1, Math.min(999, Math.round(settings.start_page || 1))),
})

const responseError = (payload: unknown, fallback: string) => {
  if (!payload || typeof payload !== 'object') return fallback
  const record = payload as Record<string, unknown>
  if (typeof record.detail === 'string') return record.detail
  if (typeof record.error === 'string') return record.error
  return fallback
}

const readJson = async (response: Response) => {
  try {
    return await response.json() as unknown
  } catch {
    return null
  }
}

export const parserSettingsEqual = (left: ParserSettings, right: ParserSettings) => (
  left.city === right.city
  && left.limit === right.limit
  && left.start_page === right.start_page
  && left.niches.join('\u0000') === right.niches.join('\u0000')
  && left.sources.join('\u0000') === right.sources.join('\u0000')
)

export const validateParserSettings = (settings: ParserSettings) => {
  if (!settings.city.trim()) throw new Error('Выберите город для парсинга')
  if (!settings.niches.length) throw new Error('Выберите хотя бы одну нишу')
  if (!settings.sources.length) throw new Error('Выберите хотя бы один источник')
}

export async function persistParserSettings(settings: ParserSettings, request: typeof fetch = fetch) {
  validateParserSettings(settings)
  const response = await request(`${API_BASE}/api/parser/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settingsPayload(settings)),
  })
  const payload = await readJson(response)
  if (!response.ok) throw new Error(responseError(payload, 'Не удалось сохранить настройки парсера'))
  return payload as ParserSettings
}

async function requestParserStart(settings: ParserSettings, request: typeof fetch) {
  const response = await request(`${API_BASE}/api/clients/parse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settingsPayload(settings)),
  })
  const payload = await readJson(response) as { job_id?: string; error?: string } | null
  if (!response.ok || !payload?.job_id) {
    throw new Error(responseError(payload, 'Не удалось запустить парсер'))
  }
  return payload.job_id
}

export async function startParserWithSettings(settings: ParserSettings, options: ParserStartOptions = {}): Promise<ParserStartResult> {
  const request = options.request ?? fetch
  const savedSettings = await persistParserSettings(settings, request)
  await options.onPersist?.(savedSettings)
  const jobId = await requestParserStart(savedSettings, request)
  return { settings: savedSettings, jobId }
}
