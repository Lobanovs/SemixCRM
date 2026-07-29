import { useEffect, useMemo, useState } from 'react'
import {
  Bookmark,
  CircleAlert,
  ExternalLink,
  Link2,
  LoaderCircle,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from 'lucide-react'

import { apiRequest } from '../api'
import './UsefulThingsPage.css'


type UsefulLink = {
  id: number
  title: string
  url: string
  description: string
  created_at: string
  updated_at: string
}

type UsefulLinksPayload = {
  items: UsefulLink[]
  stats: { total: number }
}

type LinkForm = {
  title: string
  url: string
  description: string
}

type Feedback = { kind: 'success' | 'error'; text: string } | null

const EMPTY_FORM: LinkForm = { title: '', url: '', description: '' }

function domainOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function messageFrom(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

export default function UsefulThingsPage() {
  const [items, setItems] = useState<UsefulLink[] | null>(null)
  const [query, setQuery] = useState('')
  const [form, setForm] = useState<LinkForm>(EMPTY_FORM)
  const [editing, setEditing] = useState<UsefulLink | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<UsefulLink | null>(null)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>(null)
  const [formError, setFormError] = useState('')

  const load = async () => {
    setFeedback(null)
    try {
      const payload = await apiRequest<UsefulLinksPayload>('/api/useful-links', {
        fallback: 'Не удалось загрузить полезные сайты',
      })
      setItems(payload.items)
    } catch (error) {
      setItems(null)
      setFeedback({ kind: 'error', text: messageFrom(error, 'Не удалось загрузить полезные сайты') })
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const filtered = useMemo(() => {
    if (!items) return []
    const normalized = query.trim().toLocaleLowerCase('ru')
    if (!normalized) return items
    return items.filter((item) =>
      `${item.title} ${domainOf(item.url)} ${item.description}`.toLocaleLowerCase('ru').includes(normalized),
    )
  }, [items, query])

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setFormError('')
    setFeedback(null)
    setFormOpen(true)
  }

  const openEdit = (item: UsefulLink) => {
    setEditing(item)
    setForm({ title: item.title, url: item.url, description: item.description })
    setFormError('')
    setFeedback(null)
    setFormOpen(true)
  }

  const closeForm = () => {
    if (busy) return
    setFormOpen(false)
    setEditing(null)
    setFormError('')
  }

  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    const title = form.title.trim()
    const url = form.url.trim()
    const description = form.description.trim()
    if (!title || !url) {
      setFormError('Заполните название и адрес сайта')
      return
    }
    setBusy(true)
    setFormError('')
    try {
      const saved = await apiRequest<UsefulLink>(
        editing ? `/api/useful-links/${editing.id}` : '/api/useful-links',
        {
          method: editing ? 'PUT' : 'POST',
          body: { title, url, description },
          fallback: editing ? 'Не удалось сохранить изменения' : 'Не удалось добавить сайт',
        },
      )
      setItems((current) => {
        if (!current) return [saved]
        return editing
          ? current.map((item) => item.id === saved.id ? saved : item)
          : [saved, ...current]
      })
      setFormOpen(false)
      setEditing(null)
      setFeedback({
        kind: 'success',
        text: editing ? 'Изменения сохранены' : 'Сайт добавлен',
      })
    } catch (error) {
      setFormError(messageFrom(error, 'Не удалось сохранить сайт'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!deleteTarget) return
    setBusy(true)
    setFeedback(null)
    try {
      await apiRequest(`/api/useful-links/${deleteTarget.id}`, {
        method: 'DELETE',
        fallback: 'Не удалось удалить сайт',
      })
      setItems((current) => current?.filter((item) => item.id !== deleteTarget.id) ?? [])
      setDeleteTarget(null)
      setFeedback({ kind: 'success', text: 'Сайт удалён' })
    } catch (error) {
      setDeleteTarget(null)
      setFeedback({ kind: 'error', text: messageFrom(error, 'Не удалось удалить сайт') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="data-page useful-things-page">
      <header className="useful-heading">
        <div className="page-title-block">
          <h1>Полезные вещи</h1>
          <p>Ваш рабочий каталог сайтов, сервисов и инструментов — всё нужное под рукой.</p>
        </div>
        <div className="useful-total" aria-label={`Сохранено сайтов: ${items?.length ?? 0}`}>
          <Bookmark size={18} aria-hidden="true" />
          <strong>{items?.length ?? 0}</strong>
          <span>сохранено</span>
        </div>
      </header>

      <div className="useful-toolbar">
        <label className="useful-search">
          <span className="sr-only">Поиск по полезным сайтам</span>
          <Search size={19} aria-hidden="true" />
          <input
            aria-label="Поиск по полезным сайтам"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Найти по названию, адресу или описанию"
          />
          {query && (
            <button type="button" onClick={() => setQuery('')} aria-label="Очистить поиск">
              <X size={17} />
            </button>
          )}
        </label>
        <button className="useful-add-button" type="button" onClick={openCreate}>
          <Plus size={19} />
          Добавить сайт
        </button>
      </div>

      {feedback && (
        <div
          className={`useful-feedback ${feedback.kind}`}
          role={feedback.kind === 'error' ? 'alert' : 'status'}
        >
          {feedback.kind === 'error' ? <CircleAlert size={18} /> : <Bookmark size={18} />}
          <span>{feedback.text}</span>
          {feedback.kind === 'error' && items === null && (
            <button type="button" onClick={() => void load()}>Повторить</button>
          )}
        </div>
      )}

      {items === null && !feedback ? (
        <section className="useful-state" aria-label="Загрузка полезных сайтов">
          <LoaderCircle className="is-spinning" size={30} />
          <h2>Загружаю каталог…</h2>
        </section>
      ) : items !== null && items.length === 0 ? (
        <section className="useful-state">
          <span className="useful-state-icon"><Bookmark size={30} /></span>
          <h2>Здесь будут ваши полезные сайты</h2>
          <p>Добавьте первый сервис, чтобы больше не искать рабочие ссылки по вкладкам и сообщениям.</p>
          <button type="button" onClick={openCreate}><Plus size={18} />Добавить первый сайт</button>
        </section>
      ) : items !== null && filtered.length === 0 ? (
        <section className="useful-state">
          <span className="useful-state-icon"><Search size={30} /></span>
          <h2>По запросу ничего не найдено</h2>
          <p>Попробуйте другое слово или вернитесь ко всему каталогу.</p>
          <button type="button" onClick={() => setQuery('')}>Очистить поиск</button>
        </section>
      ) : (
        <section className="useful-grid" aria-label="Сохранённые сайты">
          {filtered.map((item) => (
            <article className="useful-card" key={item.id} aria-label={`Сайт ${item.title}`}>
              <header>
                <span className="useful-card-icon" aria-hidden="true"><Link2 size={23} /></span>
                <div>
                  <h2>{item.title}</h2>
                  <span>{domainOf(item.url)}</span>
                </div>
              </header>
              <p>{item.description || 'Описание пока не добавлено.'}</p>
              <footer>
                <a
                  className="useful-open-link"
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`Открыть ${item.title}`}
                >
                  <ExternalLink size={17} />
                  Открыть
                </a>
                <div className="useful-card-actions">
                  <button type="button" onClick={() => openEdit(item)} aria-label={`Изменить ${item.title}`}>
                    <Pencil size={17} />
                  </button>
                  <button
                    className="is-danger"
                    type="button"
                    onClick={() => {
                      setFeedback(null)
                      setDeleteTarget(item)
                    }}
                    aria-label={`Удалить ${item.title}`}
                  >
                    <Trash2 size={17} />
                  </button>
                </div>
              </footer>
            </article>
          ))}
        </section>
      )}

      {formOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={closeForm}>
          <form
            className="useful-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="useful-form-title"
            onMouseDown={(event) => event.stopPropagation()}
            onSubmit={(event) => void save(event)}
          >
            <button className="modal-close" type="button" onClick={closeForm} aria-label="Закрыть форму">
              <X size={20} />
            </button>
            <span className="useful-modal-icon"><Bookmark size={24} /></span>
            <div className="useful-modal-heading">
              <h2 id="useful-form-title">{editing ? 'Изменить сайт' : 'Добавить полезный сайт'}</h2>
              <p>{editing ? 'Обновите данные сохранённого ресурса.' : 'Сохраните рабочий ресурс вместе с короткой подсказкой.'}</p>
            </div>

            <label className="useful-field">
              <span>Название</span>
              <input
                autoFocus
                aria-label="Название"
                maxLength={120}
                value={form.title}
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                placeholder="Например, Figma"
              />
            </label>
            <label className="useful-field">
              <span>Адрес сайта</span>
              <input
                aria-label="Адрес сайта"
                maxLength={2048}
                value={form.url}
                onChange={(event) => setForm((current) => ({ ...current, url: event.target.value }))}
                placeholder="figma.com"
                inputMode="url"
              />
              <small>Можно без https:// — CRM добавит его автоматически.</small>
            </label>
            <label className="useful-field">
              <span>Описание</span>
              <textarea
                aria-label="Описание"
                maxLength={1000}
                rows={4}
                value={form.description}
                onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                placeholder="Для чего пригодится этот сайт"
              />
              <small>{form.description.length}/1000</small>
            </label>

            {formError && <div className="useful-form-error" role="alert"><CircleAlert size={17} />{formError}</div>}

            <div className="useful-modal-actions">
              <button type="button" onClick={closeForm} disabled={busy}>Отмена</button>
              <button className="is-primary" type="submit" disabled={busy} aria-busy={busy}>
                {busy && <LoaderCircle className="is-spinning" size={17} />}
                {editing ? 'Сохранить изменения' : 'Сохранить сайт'}
              </button>
            </div>
          </form>
        </div>
      )}

      {deleteTarget && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => !busy && setDeleteTarget(null)}>
          <section
            className="useful-modal useful-delete-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="useful-delete-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <span className="useful-delete-icon"><Trash2 size={24} /></span>
            <h2 id="useful-delete-title">Удалить {deleteTarget.title}?</h2>
            <p>Сайт и его описание исчезнут из каталога. Это действие нельзя отменить.</p>
            <div className="useful-modal-actions">
              <button type="button" onClick={() => setDeleteTarget(null)} disabled={busy}>Оставить</button>
              <button className="is-danger" type="button" onClick={() => void remove()} disabled={busy}>
                {busy && <LoaderCircle className="is-spinning" size={17} />}
                Удалить сайт
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
