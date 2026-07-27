export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000'

/**
 * Backend отклоняет изменяющие запросы без этого заголовка: браузер не может
 * выставить его кросс-доменно без preflight, поэтому сторонний сайт не сможет
 * запустить парсер или процесс проекта из открытой вкладки.
 */
export const REQUESTED_WITH = 'SemixCRM'

export const jsonHeaders = {
  'Content-Type': 'application/json',
  'X-Requested-With': REQUESTED_WITH,
} as const

export async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json() as unknown
  } catch {
    return null
  }
}

export function responseError(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback
  const record = payload as Record<string, unknown>
  if (typeof record.detail === 'string') return record.detail
  if (typeof record.error === 'string') return record.error
  return fallback
}

type RequestOptions = {
  method?: string
  body?: unknown
  fallback?: string
  fetcher?: typeof fetch
  signal?: AbortSignal
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, fallback = 'Запрос не выполнен', fetcher = fetch, signal } = options
  const response = await fetcher(`${API_BASE}${path}`, {
    method,
    headers: jsonHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  const payload = await readJson(response)
  if (!response.ok) throw new Error(responseError(payload, fallback))
  return payload as T
}
