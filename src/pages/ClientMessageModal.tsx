import { type KeyboardEvent, useEffect, useState } from 'react'
import {
  BadgeCheck,
  Check,
  Copy,
  ExternalLink,
  Lightbulb,
  RefreshCw,
  Sparkles,
  Target,
  TriangleAlert,
  X,
} from 'lucide-react'
import { apiRequest } from '../api'
import './ClientMessageModal.css'

type MessageTone = 'confident' | 'hard_sell' | 'expert'

export type MessageVariant = {
  tone?: MessageTone | string
  title?: string
  angle?: string
  text: string
}

type MessageInsights = {
  signal?: string
  problem?: string
  opportunity?: string
}

export type ClientMessage = {
  ready: boolean
  analysis?: string
  pain?: string
  money_argument?: string
  insights?: MessageInsights
  variants?: MessageVariant[]
  follow_up?: string
  warnings?: string[]
  links?: { channel: string; url: string }[]
  cached?: boolean
  model?: string
}

const TONE_ORDER: MessageTone[] = ['confident', 'hard_sell', 'expert']

const TONE_META: Record<MessageTone, { title: string; note: string }> = {
  confident: { title: 'Уверенный продавец', note: 'Прямо и по делу' },
  hard_sell: { title: 'Жёсткая продажа', note: 'Сильнее через цену бездействия' },
  expert: { title: 'Эксперт', note: 'Спокойно через диагностику' },
}

function toneFor(variant: MessageVariant, index: number): MessageTone {
  return TONE_ORDER.includes(variant.tone as MessageTone)
    ? variant.tone as MessageTone
    : TONE_ORDER[index] ?? 'confident'
}

function variantTitle(variant: MessageVariant, index: number): string {
  return variant.title || variant.angle || TONE_META[toneFor(variant, index)].title
}

export default function ClientMessageModal({
  clientId, clientName, enabled, onClose, onSent,
}: {
  clientId: number
  clientName: string
  enabled: boolean
  onClose: () => void
  onSent: () => void
}) {
  const [message, setMessage] = useState<ClientMessage | null>(null)
  const [active, setActive] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')

  const generate = async (force: boolean) => {
    setBusy(true)
    setError('')
    try {
      const result = await apiRequest<ClientMessage>(
        `/api/ai/clients/${clientId}/message${force ? '?force=true' : ''}`,
        { method: 'POST', fallback: 'Не удалось подготовить сообщение' },
      )
      setMessage(result)
      setActive(0)
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : 'Не удалось подготовить сообщение')
    } finally {
      setBusy(false)
    }
  }

  // Сохранённый разбор показываем сразу, а модель дёргаем только по кнопке.
  useEffect(() => {
    if (!enabled) return
    void (async () => {
      try {
        const stored = await apiRequest<ClientMessage>(`/api/ai/clients/${clientId}/message`, { fallback: '' })
        if (stored.ready) { setMessage(stored); return }
      } catch { /* нет сохранённого разбора — это нормально */ }
      await generate(false)
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, enabled])

  // Кнопку показываем всегда: спрятанная функция — это функция, о которой никто не узнает.
  // Вместо мёртвого клика объясняем, чего не хватает.
  if (!enabled) return <SetupDialog clientName={clientName} onClose={onClose} />

  const variants = message?.variants ?? []
  const current = variants[active]
  const currentTone = current ? toneFor(current, active) : 'confident'
  const insights = {
    signal: message?.insights?.signal || message?.analysis || 'Фактов для разбора пока недостаточно.',
    problem: message?.insights?.problem || message?.pain || 'Гипотеза появится после новой генерации.',
    opportunity: message?.insights?.opportunity || message?.money_argument || 'Возможность появится после новой генерации.',
  }

  const copy = async (text: string, key: string) => {
    await navigator.clipboard?.writeText(text)
    setCopied(key)
    window.setTimeout(() => setCopied(''), 1600)
  }

  const selectTabFromKeyboard = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const next = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? variants.length - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + variants.length) % variants.length
    setActive(next)
    window.requestAnimationFrame(() => document.getElementById(`ai-tone-tab-${next}`)?.focus())
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="compact-modal client-message-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="client-message-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="ai-workspace-header">
          <span className="ai-workspace-mark" aria-hidden="true"><Sparkles size={20} /></span>
          <div className="ai-workspace-heading">
            <span className="ai-workspace-kicker">AI-ассистент продаж</span>
            <h2 id="client-message-title">Первое сообщение <strong>{clientName}</strong></h2>
            <div className="ai-workspace-meta" aria-live="polite">
              <span>3 стратегии</span>
              {message?.model && <span>{message.model}</span>}
              {message?.cached && <span>Сохранённый результат</span>}
              {busy && <span>Обновляю варианты…</span>}
            </div>
          </div>
          <button className="ai-workspace-close" type="button" onClick={onClose} aria-label="Закрыть">
            <X size={20} />
          </button>
        </header>

        {!message && (
          <div className="ai-workspace-state">
            {busy ? (
              <>
                <span className="ai-state-loader" aria-hidden="true" />
                <h3>Готовлю три стратегии</h3>
                <p>Проверяю факты карточки и собираю сообщения без рекламных штампов.</p>
              </>
            ) : (
              <>
                <span className="ai-state-error" aria-hidden="true"><TriangleAlert size={22} /></span>
                <h3>Не удалось получить варианты</h3>
                <p className="field-error" role="alert">{error || 'Модель не вернула готовый ответ.'}</p>
                <button className="ai-retry-action" type="button" onClick={() => void generate(true)}>
                  <RefreshCw size={16} /> Повторить
                </button>
              </>
            )}
          </div>
        )}

        {message && (
          <div className="ai-workspace-grid">
            <aside className="ai-insight-column" aria-label="Разбор карточки">
              <div className="ai-column-heading">
                <span>Перед сообщением</span>
                <h3>Короткий разбор</h3>
              </div>
              <article className="ai-insight-card signal">
                <span className="ai-insight-icon" aria-hidden="true"><BadgeCheck size={17} /></span>
                <div><h4>Сильный сигнал</h4><p>{insights.signal}</p></div>
              </article>
              <article className="ai-insight-card problem">
                <span className="ai-insight-icon" aria-hidden="true"><Target size={17} /></span>
                <div><h4>Гипотеза</h4><p>{insights.problem}</p></div>
              </article>
              <article className="ai-insight-card opportunity">
                <span className="ai-insight-icon" aria-hidden="true"><Lightbulb size={17} /></span>
                <div><h4>Возможность</h4><p>{insights.opportunity}</p></div>
              </article>
              <p className="ai-grounding-note">
                AI использует только данные карточки. Проверьте текст перед отправкой.
              </p>
            </aside>

            <main className="ai-compose-column">
              {error && (
                <div className="ai-inline-error" role="alert">
                  <TriangleAlert size={17} />
                  <span>{error}</span>
                  <button type="button" onClick={() => void generate(true)} disabled={busy}>Повторить</button>
                </div>
              )}

              <div className="ai-tone-tabs" role="tablist" aria-label="Стратегии сообщения">
                {variants.map((variant, index) => {
                  const tone = toneFor(variant, index)
                  return (
                    <button
                      id={`ai-tone-tab-${index}`}
                      className={index === active ? `active ${tone}` : tone}
                      type="button"
                      role="tab"
                      aria-selected={index === active}
                      aria-controls={`ai-tone-panel-${index}`}
                      tabIndex={index === active ? 0 : -1}
                      key={`${tone}-${index}`}
                      onClick={() => setActive(index)}
                      onKeyDown={(event) => selectTabFromKeyboard(event, index)}
                    >
                      <strong>{variantTitle(variant, index)}</strong>
                      <span>{TONE_META[tone].note}</span>
                    </button>
                  )
                })}
              </div>

              {current && (
                <section
                  id={`ai-tone-panel-${active}`}
                  className="ai-compose-panel"
                  role="tabpanel"
                  aria-labelledby={`ai-tone-tab-${active}`}
                >
                  <div className="ai-editor-heading">
                    <div>
                      <label htmlFor="ai-message-editor">Текст сообщения</label>
                      <span>{TONE_META[currentTone].note}</span>
                    </div>
                    <span className={(current.text.length >= 180 && current.text.length <= 320) ? 'valid' : ''}>
                      {current.text.length} / 320
                    </span>
                  </div>
                  <textarea
                    id="ai-message-editor"
                    className="ai-compose-textarea"
                    aria-label="Текст сообщения"
                    value={current.text}
                    rows={8}
                    onChange={(event) => {
                      const edited = [...variants]
                      edited[active] = { ...edited[active], text: event.target.value }
                      setMessage((currentMessage) => (
                        currentMessage ? { ...currentMessage, variants: edited } : currentMessage
                      ))
                    }}
                  />

                  {(message.warnings ?? []).length > 0 && (
                    <div className="ai-warnings">
                      {(message.warnings ?? []).map((warning) => (
                        <p key={warning}><TriangleAlert size={14} />{warning}</p>
                      ))}
                    </div>
                  )}

                  {message.follow_up && (
                    <details className="ai-follow-up-panel">
                      <summary>Сообщение через три дня</summary>
                      <p>{message.follow_up}</p>
                      <button type="button" onClick={() => void copy(message.follow_up ?? '', 'follow')}>
                        {copied === 'follow' ? <Check size={15} /> : <Copy size={15} />}
                        {copied === 'follow' ? 'Скопировано' : 'Скопировать напоминание'}
                      </button>
                    </details>
                  )}
                </section>
              )}
            </main>
          </div>
        )}

        <footer className="ai-workspace-actions">
          <div className="ai-primary-actions">
            {current && (
              <button className="ai-copy-action" type="button" onClick={() => void copy(current.text, 'text')}>
                {copied === 'text' ? <Check size={17} /> : <Copy size={17} />}
                {copied === 'text' ? 'Скопировано' : 'Скопировать'}
              </button>
            )}
            {current && (message?.links ?? []).map((link) => (
              <a
                className={`ai-messenger-action ${link.channel.toLowerCase()}`}
                key={link.channel}
                href={link.channel === 'WhatsApp'
                  ? `${link.url.split('?')[0]}?text=${encodeURIComponent(current.text)}`
                  : link.url}
                target="_blank"
                rel="noreferrer"
                onClick={onSent}
              >
                Открыть {link.channel} <ExternalLink size={15} />
              </a>
            ))}
          </div>
          {message && (
            <button className="ai-regenerate-action" type="button" onClick={() => void generate(true)} disabled={busy}>
              <RefreshCw size={17} />{busy ? 'Переписываю…' : 'Переписать 3 варианта'}
            </button>
          )}
        </footer>
      </section>
    </div>
  )
}

function SetupDialog({ clientName, onClose }: { clientName: string; onClose: () => void }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="compact-modal client-message-modal ai-setup-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-setup-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button>
        <span className="metric-icon purple"><Sparkles /></span>
        <h2 id="ai-setup-title">Первое сообщение: {clientName}</h2>
        <p className="field-hint">Черновики пишет модель, а ключа к ней пока нет — поэтому генерировать нечем.</p>

        <div className="ai-setup-preview">
          <h3>Что появится в этом окне</h3>
          <ul>
            <li>Короткий разбор: сильный сигнал, гипотеза и возможность</li>
            <li>Три стратегии: уверенный продавец, жёсткая продажа и эксперт</li>
            <li>Редактирование каждого сообщения перед отправкой</li>
            <li>Напоминание, если через три дня не ответят</li>
            <li>Отправка в WhatsApp с уже подставленным текстом</li>
          </ul>
        </div>

        <div className="ai-setup-steps">
          <h3>Как включить</h3>
          <ol>
            <li>Скопируйте API-ключ своей подписки OpenCode Go.</li>
            <li>Откройте раздел «Настройки» и вставьте ключ в форму OpenCode Go.</li>
            <li>Проверьте подключение и сохраните — перезапуск backend не нужен.</li>
          </ol>
        </div>
      </section>
    </div>
  )
}
