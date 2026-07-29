import { type KeyboardEvent, useEffect, useState } from 'react'
import {
  BadgeCheck,
  Check,
  Copy,
  ExternalLink,
  FileText,
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
  status?: 'ready' | 'stale' | 'missing'
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
  created_at?: string
  manual_observation?: string
  portfolio_url?: string
  review_insight?: { summary?: string; evidence_ids?: string[] }
  review_evidence?: { id: string; text: string }[]
}

const TONE_ORDER: MessageTone[] = ['confident', 'hard_sell', 'expert']

const TONE_META: Record<MessageTone, { title: string; note: string }> = {
  confident: { title: 'Цены и информация', note: 'Как клиент узнаёт нужные детали' },
  hard_sell: { title: 'Запись и заявки', note: 'Как устроен путь до обращения' },
  expert: { title: 'Обработка обращений', note: 'Что происходит, когда сразу ответить не могут' },
}

const TONE_LENGTHS: Record<MessageTone, [number, number]> = {
  confident: [70, 260],
  hard_sell: [70, 260],
  expert: [70, 260],
}

const CONVERSATION_STAGES = [
  { step: 2, title: 'Найти слабое место', note: 'Уточнить, что происходит, когда текущий процесс не срабатывает.' },
  { step: 3, title: 'Помочь увидеть последствия', note: 'Проверить вместе, может ли из-за этого потеряться обращение.' },
  { step: 4, title: 'Уточнить желаемый результат', note: 'Спросить, какой процесс был бы удобнее для бизнеса.' },
  { step: 5, title: 'Показать решение', note: 'Только после подтверждения проблемы показать подходящее решение.' },
  { step: 6, title: 'Подтвердить компетентность', note: 'Здесь уже уместны портфолио, кейсы и короткое представление.' },
  { step: 7, title: 'Предложить следующий шаг', note: 'Предложить конкретное время короткого показа или обсуждения.' },
] as const

function toneFor(variant: MessageVariant, index: number): MessageTone {
  return TONE_ORDER.includes(variant.tone as MessageTone)
    ? variant.tone as MessageTone
    : TONE_ORDER[index] ?? 'confident'
}

function variantTitle(variant: MessageVariant, index: number): string {
  return variant.title || variant.angle || TONE_META[toneFor(variant, index)].title
}

export default function ClientMessageModal({
  clientId, clientName, enabled, onClose, onSent, onGenerated,
}: {
  clientId: number
  clientName: string
  enabled: boolean
  onClose: () => void
  onSent: () => void
  onGenerated?: () => void
}) {
  const [message, setMessage] = useState<ClientMessage | null>(null)
  const [active, setActive] = useState(0)
  const [busy, setBusy] = useState(false)
  const [storedLoading, setStoredLoading] = useState(enabled)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')
  const [manualObservation, setManualObservation] = useState('')
  const [storedStatus, setStoredStatus] = useState<'ready' | 'stale' | 'missing'>('missing')

  const generate = async (force: boolean) => {
    setBusy(true)
    setError('')
    try {
      const result = await apiRequest<ClientMessage>(
        `/api/ai/clients/${clientId}/message${force ? '?force=true' : ''}`,
        {
          method: 'POST',
          body: { manual_observation: manualObservation.trim() },
          fallback: 'Не удалось подготовить сообщение',
        },
      )
      setMessage(result)
      setStoredStatus('ready')
      setActive(0)
      onGenerated?.()
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : 'Не удалось подготовить сообщение')
    } finally {
      setBusy(false)
    }
  }

  // Сохранённый разбор показываем сразу, а модель дёргаем только по кнопке.
  useEffect(() => {
    if (!enabled) {
      setStoredLoading(false)
      return
    }
    const controller = new AbortController()
    void (async () => {
      try {
        const stored = await apiRequest<ClientMessage>(
          `/api/ai/clients/${clientId}/message`,
          { fallback: '', signal: controller.signal },
        )
        setStoredStatus(stored.status ?? (stored.ready ? 'ready' : 'missing'))
        if (stored.ready) {
          setManualObservation(stored.manual_observation ?? '')
          setMessage(stored)
        }
      } catch { /* нет сохранённого разбора — это нормально */ }
      finally { setStoredLoading(false) }
    })()
    return () => controller.abort()
  }, [clientId, enabled])

  // Кнопку показываем всегда: спрятанная функция — это функция, о которой никто не узнает.
  // Вместо мёртвого клика объясняем, чего не хватает.
  if (!enabled) return <SetupDialog clientName={clientName} onClose={onClose} />

  const variants = message?.variants ?? []
  const current = variants[active]
  const currentTone = current ? toneFor(current, active) : 'confident'
  const currentRange = TONE_LENGTHS[currentTone]
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
            <h2 id="client-message-title">Первое диагностическое сообщение: <strong>{clientName}</strong></h2>
            <div className="ai-workspace-meta" aria-live="polite">
              <span>3 коротких вопроса</span>
              {message?.model && <span>{message.model}</span>}
              {message?.cached && <span>Сохранённый результат</span>}
              {busy && <span>Изучаю карточку и отзывы…</span>}
            </div>
          </div>
          <button className="ai-workspace-close" type="button" onClick={onClose} aria-label="Закрыть">
            <X size={20} />
          </button>
        </header>

        {storedLoading && !message && (
          <div className="ai-workspace-state">
            <span className="ai-state-loader" aria-hidden="true" />
            <h3>Проверяю сохранённый текст</h3>
            <p>Это не запускает нейросеть и не расходует запрос.</p>
          </div>
        )}

        {!storedLoading && !message && (
          <div className="ai-generator-start">
            <span className="ai-generator-icon" aria-hidden="true"><FileText size={24} /></span>
            <div className="ai-generator-copy">
              <span className="ai-generator-kicker">
                {storedStatus === 'stale' ? 'Сохранённые вопросы устарели' : 'Вопросы ещё не созданы'}
              </span>
              <h3>{storedStatus === 'stale' ? 'Обновите вопросы по актуальной карточке' : 'Начните разговор с диагностики'}</h3>
              <p>
                Нейросеть изучит карточку и отзывы 2GIS, а затем предложит три коротких вопроса о текущем процессе.
                Без ссылки, портфолио и продажи — генерация начнётся только после нажатия кнопки.
              </p>
            </div>
            <div className="ai-generator-form">
              <label htmlFor="ai-manual-observation">Наблюдение о клиенте (необязательно)</label>
              <textarea
                id="ai-manual-observation"
                value={manualObservation}
                maxLength={500}
                rows={4}
                onChange={(event) => setManualObservation(event.target.value)}
                placeholder="Например: в отзывах часто хвалят мастера Анну, а запись доступна только по телефону"
              />
              <span className="ai-generator-help">
                Добавьте только проверенный факт. Если поле оставить пустым, AI возьмёт данные карточки и отзывы 2GIS.
              </span>
              {error && <p className="ai-generator-error" role="alert"><TriangleAlert size={16} />{error}</p>}
              <button className="ai-generate-action" type="button" onClick={() => void generate(storedStatus === 'stale')} disabled={busy}>
                {busy ? <span className="ai-button-loader" aria-hidden="true" /> : <Sparkles size={18} />}
                {busy ? 'Изучаю клиента и пишу…' : 'Сгенерировать 3 вопроса'}
              </button>
            </div>
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
              {message.review_insight?.summary && (
                <article className="ai-review-proof">
                  <span>Что заметили в отзывах</span>
                  <p>{message.review_insight.summary}</p>
                  <small>
                    Подтверждено отзывами: {message.review_insight.evidence_ids?.join(', ') || '2GIS'}
                  </small>
                </article>
              )}
              <p className="ai-grounding-note">
                AI использует данные карточки и только найденные отзывы 2GIS. Проверьте текст перед отправкой.
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

              <div className="ai-compose-options">
                <label htmlFor="ai-manual-observation-ready">
                  Наблюдение о клиенте
                  <textarea
                    id="ai-manual-observation-ready"
                    value={manualObservation}
                    maxLength={500}
                    rows={2}
                    onChange={(event) => setManualObservation(event.target.value)}
                    placeholder="Можно уточнить факт перед повторной генерацией"
                  />
                </label>
              </div>

              <div className="ai-tone-tabs" role="tablist" aria-label="Диагностические вопросы">
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
                      <label htmlFor="ai-message-editor">Первый диагностический вопрос</label>
                      <span>{TONE_META[currentTone].note}</span>
                    </div>
                    <span className={(current.text.length >= currentRange[0] && current.text.length <= currentRange[1]) ? 'valid' : ''}>
                      {current.text.length} символов
                    </span>
                  </div>
                  <textarea
                    id="ai-message-editor"
                    className="ai-compose-textarea"
                    aria-label="Первый диагностический вопрос"
                    value={current.text}
                    rows={5}
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

                  <details className="ai-conversation-map">
                    <summary>Что делать после ответа</summary>
                    <p className="ai-conversation-intro">
                      Не переходите к решению, пока клиент сам не подтвердил слабое место.
                    </p>
                    <div className="ai-conversation-stages">
                      {CONVERSATION_STAGES.map((stage) => (
                        <article className="ai-conversation-stage" key={stage.step}>
                          <span aria-hidden="true">{stage.step}</span>
                          <div><strong>{stage.title}</strong><p>{stage.note}</p></div>
                        </article>
                      ))}
                    </div>
                  </details>
                </section>
              )}
            </main>
          </div>
        )}

        {message && <footer className="ai-workspace-actions">
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
          <button className="ai-regenerate-action" type="button" onClick={() => void generate(true)} disabled={busy}>
            <RefreshCw size={17} />{busy ? 'Переписываю…' : 'Переписать 3 вопроса'}
          </button>
        </footer>}
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
            <li>Три коротких вопроса: о ценах, записи и обработке обращений</li>
            <li>Редактирование каждого сообщения перед отправкой</li>
            <li>Карта следующих этапов консультативной продажи</li>
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
