import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  CircleAlert,
  Cpu,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  PlugZap,
  Save,
  Settings2,
  ShieldCheck,
  Timer,
  Trash2,
  X,
} from 'lucide-react'

import { apiRequest } from '../api'
import './SettingsPage.css'


type SupportedModel = {
  id: string
  label: string
}

type AiSettings = {
  enabled: boolean
  api_key_configured: boolean
  api_key_hint: string
  api_key_source: string
  model: string
  base_url: string
  timeout: number
  updated_at: string
  supported_models: SupportedModel[]
}

type DeleteResponse = {
  ok: boolean
  removed: boolean
  settings: AiSettings
}

type TestResponse = {
  ok: boolean
  message: string
  model: string
}

type BusyAction = 'load' | 'save' | 'test' | 'delete' | ''
type Feedback = { kind: 'success' | 'error'; text: string } | null


export default function SettingsPage() {
  const [settings, setSettings] = useState<AiSettings | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [timeout, setTimeoutValue] = useState(90)
  const [showKey, setShowKey] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [busy, setBusy] = useState<BusyAction>('load')
  const [feedback, setFeedback] = useState<Feedback>(null)

  const applySettings = (next: AiSettings) => {
    setSettings(next)
    setModel(next.model)
    setTimeoutValue(next.timeout)
  }

  const load = async () => {
    setBusy('load')
    setFeedback(null)
    try {
      applySettings(await apiRequest<AiSettings>('/api/ai/settings', {
        fallback: 'Не удалось загрузить настройки OpenCode Go',
      }))
    } catch (error) {
      setFeedback({ kind: 'error', text: error instanceof Error ? error.message : 'Не удалось загрузить настройки' })
    } finally {
      setBusy('')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const formPayload = () => {
    const payload: { api_key?: string; model: string; timeout: number } = { model, timeout }
    const key = apiKey.trim()
    if (key) payload.api_key = key
    return payload
  }

  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy('save')
    setFeedback(null)
    try {
      const saved = await apiRequest<AiSettings>('/api/ai/settings', {
        method: 'PUT',
        body: formPayload(),
        fallback: 'Не удалось сохранить настройки',
      })
      applySettings(saved)
      setApiKey('')
      setShowKey(false)
      setConfirmRemove(false)
      setFeedback({ kind: 'success', text: 'Настройки сохранены и уже применяются' })
    } catch (error) {
      setFeedback({ kind: 'error', text: error instanceof Error ? error.message : 'Не удалось сохранить настройки' })
    } finally {
      setBusy('')
    }
  }

  const testConnection = async () => {
    if (!apiKey.trim() && !settings?.api_key_configured) {
      setFeedback({ kind: 'error', text: 'Сначала вставьте API-ключ OpenCode Go' })
      return
    }
    setBusy('test')
    setFeedback(null)
    try {
      const result = await apiRequest<TestResponse>('/api/ai/settings/test', {
        method: 'POST',
        body: formPayload(),
        fallback: 'Не удалось проверить подключение',
      })
      setFeedback({ kind: 'success', text: `${result.message}. Модель: ${result.model}` })
    } catch (error) {
      setFeedback({ kind: 'error', text: error instanceof Error ? error.message : 'Не удалось проверить подключение' })
    } finally {
      setBusy('')
    }
  }

  const removeKey = async () => {
    setBusy('delete')
    setFeedback(null)
    try {
      const result = await apiRequest<DeleteResponse>('/api/ai/settings/key', {
        method: 'DELETE',
        fallback: 'Не удалось удалить ключ',
      })
      applySettings(result.settings)
      setApiKey('')
      setShowKey(false)
      setConfirmRemove(false)
      setFeedback({ kind: 'success', text: 'Сохранённый ключ удалён' })
    } catch (error) {
      setFeedback({ kind: 'error', text: error instanceof Error ? error.message : 'Не удалось удалить ключ' })
    } finally {
      setBusy('')
    }
  }

  if (!settings && busy === 'load') {
    return (
      <div className="data-page settings-page">
        <header className="page-title-block">
          <h1>Настройки</h1>
          <p>Подключение нейросети и параметры локальной CRM</p>
        </header>
        <section className="settings-loading" aria-label="Загрузка настроек">
          <LoaderCircle className="is-spinning" size={28} />
          <span>Загружаю настройки OpenCode Go…</span>
        </section>
      </div>
    )
  }

  if (!settings) {
    return (
      <div className="data-page settings-page">
        <header className="page-title-block">
          <h1>Настройки</h1>
          <p>Подключение нейросети и параметры локальной CRM</p>
        </header>
        <section className="settings-load-error">
          <CircleAlert size={28} />
          <h2>Настройки не загрузились</h2>
          {feedback?.kind === 'error' && <p role="alert">{feedback.text}</p>}
          <button className="settings-secondary-button" type="button" onClick={() => void load()}>
            Попробовать ещё раз
          </button>
        </section>
      </div>
    )
  }

  const isBusy = Boolean(busy)

  return (
    <div className="data-page settings-page">
      <header className="page-title-block settings-page-heading">
        <div>
          <h1>Настройки</h1>
          <p>Подключите OpenCode Go для генерации персональных сообщений клиентам</p>
        </div>
        <a href="https://opencode.ai/docs/go/" target="_blank" rel="noreferrer" className="settings-docs-link">
          Документация OpenCode Go
        </a>
      </header>

      <section className={`ai-connection-card ${settings.enabled ? 'is-connected' : 'is-disconnected'}`}>
        <span className="ai-connection-icon" aria-hidden="true">
          {settings.enabled ? <ShieldCheck /> : <KeyRound />}
        </span>
        <div className="ai-connection-copy">
          <span className="ai-connection-eyebrow">Нейросеть</span>
          <h2>{settings.enabled ? 'OpenCode Go подключён' : 'OpenCode Go не настроен'}</h2>
          <p>
            {settings.enabled
              ? `Ключ ${settings.api_key_hint} готов к работе с моделью ${settings.model}.`
              : 'Вставьте ключ подписки OpenCode Go — после сохранения перезапуск не потребуется.'}
          </p>
        </div>
        <span className="ai-connection-badge">
          {settings.enabled ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}
          {settings.enabled ? 'Активно' : 'Нужен ключ'}
        </span>
      </section>

      <div className="settings-layout">
        <form className="settings-panel ai-settings-form" onSubmit={(event) => void save(event)}>
          <header className="settings-panel-heading">
            <span className="settings-panel-icon"><Settings2 /></span>
            <div>
              <h2>OpenCode Go</h2>
              <p>Ключ и модель для AI-функций Semix CRM</p>
            </div>
          </header>

          <div className="settings-field">
            <label htmlFor="opencode-api-key">API-ключ OpenCode Go</label>
            <div className="settings-secret-input">
              <KeyRound size={19} aria-hidden="true" />
              <input
                id="opencode-api-key"
                type={showKey ? 'text' : 'password'}
                autoComplete="off"
                spellCheck={false}
                value={apiKey}
                placeholder={settings.api_key_configured ? 'Вставьте новый ключ для замены' : 'Вставьте ключ OpenCode Go'}
                onChange={(event) => setApiKey(event.target.value)}
                disabled={isBusy}
              />
              <button
                type="button"
                aria-label={showKey ? 'Скрыть API-ключ' : 'Показать API-ключ'}
                title={showKey ? 'Скрыть API-ключ' : 'Показать API-ключ'}
                onClick={() => setShowKey((current) => !current)}
                disabled={isBusy}
              >
                {showKey ? <EyeOff size={19} /> : <Eye size={19} />}
              </button>
            </div>
            <p className="settings-field-hint">
              {settings.api_key_configured
                ? <>Сейчас сохранён ключ <strong>{settings.api_key_hint}</strong>. Пустое поле оставит его без изменений.</>
                : 'Ключ останется в локальной базе на этом компьютере и не попадёт в Git.'}
            </p>
          </div>

          <div className="settings-fields-row">
            <div className="settings-field">
              <label htmlFor="opencode-model">Модель</label>
              <div className="settings-control-with-icon">
                <Cpu size={19} aria-hidden="true" />
                <select
                  id="opencode-model"
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  disabled={isBusy}
                >
                  {settings.supported_models.map((item) => (
                    <option key={item.id} value={item.id}>{item.label}</option>
                  ))}
                </select>
              </div>
              <p className="settings-field-hint">Только модели OpenCode Go с поддержкой chat/completions.</p>
            </div>

            <div className="settings-field">
              <label htmlFor="opencode-timeout">Таймаут, секунд</label>
              <div className="settings-control-with-icon">
                <Timer size={19} aria-hidden="true" />
                <input
                  id="opencode-timeout"
                  type="number"
                  min={5}
                  max={300}
                  step={1}
                  value={timeout}
                  onChange={(event) => setTimeoutValue(Number(event.target.value))}
                  disabled={isBusy}
                />
              </div>
              <p className="settings-field-hint">Допустимый диапазон: от 5 до 300 секунд.</p>
            </div>
          </div>

          <div className="settings-field">
            <label htmlFor="opencode-endpoint">Адрес API</label>
            <div className="settings-control-with-icon is-readonly">
              <LockKeyhole size={19} aria-hidden="true" />
              <input id="opencode-endpoint" value={settings.base_url} readOnly />
            </div>
            <p className="settings-field-hint">Фиксированный официальный endpoint OpenCode Go.</p>
          </div>

          {feedback && (
            <div className={`settings-feedback is-${feedback.kind}`} role={feedback.kind === 'error' ? 'alert' : 'status'}>
              {feedback.kind === 'success' ? <CheckCircle2 size={18} /> : <CircleAlert size={18} />}
              <span>{feedback.text}</span>
            </div>
          )}

          <footer className="settings-form-actions">
            <button className="settings-primary-button" type="submit" disabled={isBusy}>
              {busy === 'save' ? <LoaderCircle className="is-spinning" size={18} /> : <Save size={18} />}
              {busy === 'save' ? 'Сохраняю…' : 'Сохранить настройки'}
            </button>
            <button className="settings-secondary-button" type="button" onClick={() => void testConnection()} disabled={isBusy}>
              {busy === 'test' ? <LoaderCircle className="is-spinning" size={18} /> : <PlugZap size={18} />}
              {busy === 'test' ? 'Проверяю…' : 'Проверить подключение'}
            </button>
          </footer>
        </form>

        <aside className="settings-side-column">
          <section className="settings-panel settings-security-card">
            <span className="settings-panel-icon is-green"><ShieldCheck /></span>
            <h2>Ключ остаётся локально</h2>
            <p>Semix CRM хранит его в локальной SQLite-базе внутри исключённой из Git папки <code>backend/data</code>.</p>
            <ul>
              <li><CheckCircle2 size={16} />API никогда не возвращает ключ целиком</li>
              <li><CheckCircle2 size={16} />Настройки применяются без перезапуска</li>
              <li><CheckCircle2 size={16} />Ключ отправляется только в OpenCode Go</li>
            </ul>
          </section>

          {settings.api_key_configured && (
            <section className="settings-panel settings-danger-card">
              <span className="settings-panel-icon is-red"><Trash2 /></span>
              <h2>Удалить ключ</h2>
              <p>AI-кнопки перестанут работать, пока вы не сохраните новый ключ.</p>
              {!confirmRemove ? (
                <button
                  className="settings-danger-button"
                  type="button"
                  onClick={() => {
                    setConfirmRemove(true)
                    setFeedback(null)
                  }}
                  disabled={isBusy}
                >
                  <Trash2 size={17} />Удалить сохранённый ключ
                </button>
              ) : (
                <div className="settings-delete-confirm" role="group" aria-label="Подтверждение удаления ключа">
                  <p>Точно удалить? Генерация сообщений перестанет работать.</p>
                  <div>
                    <button className="settings-danger-button" type="button" onClick={() => void removeKey()} disabled={isBusy}>
                      {busy === 'delete' ? <LoaderCircle className="is-spinning" size={17} /> : <Trash2 size={17} />}
                      {busy === 'delete' ? 'Удаляю…' : 'Да, удалить ключ'}
                    </button>
                    <button className="settings-icon-cancel" type="button" aria-label="Отменить удаление" onClick={() => setConfirmRemove(false)} disabled={isBusy}>
                      <X size={18} />
                    </button>
                  </div>
                </div>
              )}
            </section>
          )}
        </aside>
      </div>
    </div>
  )
}
