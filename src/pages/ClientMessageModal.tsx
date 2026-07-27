import { useEffect, useState } from 'react'
import { Check, Copy, ExternalLink, RefreshCw, Sparkles, TriangleAlert, X } from 'lucide-react'
import { apiRequest } from '../api'

export type MessageVariant = { angle: string; text: string }

export type ClientMessage = {
  ready: boolean
  analysis?: string
  pain?: string
  money_argument?: string
  variants?: MessageVariant[]
  follow_up?: string
  warnings?: string[]
  links?: { channel: string; url: string }[]
  cached?: boolean
  model?: string
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

  const copy = async (text: string, key: string) => {
    await navigator.clipboard?.writeText(text)
    setCopied(key)
    window.setTimeout(() => setCopied(''), 1600)
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
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button>
        <span className="metric-icon purple"><Sparkles /></span>
        <h2 id="client-message-title">Первое сообщение: {clientName}</h2>

        {busy && !message && <p className="field-hint">Разбираю карточку и подбираю формулировки…</p>}
        {error && <p className="field-error" role="alert">{error}</p>}

        {message?.analysis && (
          <div className="ai-analysis">
            <h3>Что видно по карточке</h3>
            <p>{message.analysis}</p>
            {message.pain && <p className="ai-pain"><strong>Боль:</strong> {message.pain}</p>}
            {message.money_argument && <p className="ai-money"><strong>Аргумент про деньги:</strong> {message.money_argument}</p>}
          </div>
        )}

        {variants.length > 0 && (
          <>
            <div className="ai-variant-tabs" role="tablist" aria-label="Варианты сообщения">
              {variants.map((variant, index) => (
                <button
                  className={index === active ? 'active' : ''}
                  type="button"
                  role="tab"
                  aria-selected={index === active}
                  key={variant.angle + index}
                  onClick={() => setActive(index)}
                >
                  {variant.angle}
                </button>
              ))}
            </div>

            <textarea
              className="ai-message-text"
              aria-label="Текст сообщения"
              value={current?.text ?? ''}
              rows={8}
              onChange={(event) => {
                const edited = [...variants]
                edited[active] = { ...edited[active], text: event.target.value }
                setMessage((current) => (current ? { ...current, variants: edited } : current))
              }}
            />
            <p className="field-hint">{(current?.text ?? '').length} символов · текст можно поправить перед отправкой</p>

            <div className="ai-send-row">
              <button type="button" onClick={() => void copy(current?.text ?? '', 'text')}>
                {copied === 'text' ? <Check size={16} /> : <Copy size={16} />}
                {copied === 'text' ? 'Скопировано' : 'Скопировать'}
              </button>
              {(message?.links ?? []).map((link) => (
                <a
                  className="ai-send-link"
                  key={link.channel}
                  href={link.channel === 'WhatsApp'
                    ? `${link.url.split('?')[0]}?text=${encodeURIComponent(current?.text ?? '')}`
                    : link.url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={onSent}
                >
                  Открыть {link.channel} <ExternalLink size={14} />
                </a>
              ))}
            </div>
          </>
        )}

        {message?.follow_up && (
          <div className="ai-follow-up">
            <h3>Если через три дня не ответят</h3>
            <p>{message.follow_up}</p>
            <button className="text-link" type="button" onClick={() => void copy(message.follow_up ?? '', 'follow')}>
              {copied === 'follow' ? 'Скопировано' : 'Скопировать напоминание'}
            </button>
          </div>
        )}

        {(message?.warnings ?? []).length > 0 && (
          <div className="ai-warnings">
            {(message?.warnings ?? []).map((warning) => (
              <p key={warning}><TriangleAlert size={13} />{warning}</p>
            ))}
          </div>
        )}

        <div className="ai-modal-footer">
          <button className="secondary-wide-action" type="button" onClick={() => void generate(true)} disabled={busy}>
            <RefreshCw size={16} />{busy ? 'Переписываю…' : 'Переписать заново'}
          </button>
          {message?.cached && <span className="field-hint">Показан сохранённый разбор</span>}
        </div>
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
            <li>Разбор карточки: рейтинг, отзывы, есть ли настоящий сайт</li>
            <li>Боль клиента и аргумент про деньги в рублях</li>
            <li>Три варианта сообщения: наблюдение, деньги, короткий</li>
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
