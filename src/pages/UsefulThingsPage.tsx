import { useEffect, useMemo, useState } from 'react'
import {
  Bookmark,
  Boxes,
  CircleAlert,
  Clipboard,
  ExternalLink,
  FileText,
  Globe2,
  LayoutGrid,
  LoaderCircle,
  Pencil,
  Plus,
  Search,
  ShoppingBag,
  Sparkles,
  Trash2,
  X,
  type LucideIcon,
} from 'lucide-react'

import { apiRequest } from '../api'
import './UsefulThingsPage.css'


type UsefulCategory = 'prompt' | 'website' | 'shop' | 'article' | 'other'
type CategoryFilter = 'all' | UsefulCategory

type UsefulLink = {
  id: number
  title: string
  category: UsefulCategory
  url: string
  description: string
  created_at: string
  updated_at: string
}

type UsefulLinksPayload = {
  items: UsefulLink[]
  stats: {
    total: number
    categories?: Partial<Record<UsefulCategory, number>>
  }
}

type LinkForm = {
  title: string
  category: UsefulCategory
  url: string
  description: string
}

type Feedback = { kind: 'success' | 'error'; text: string } | null

type CategoryMeta = {
  label: string
  itemName: string
  cardName: string
  addedText: string
  emptyTitle: string
  emptyText: string
  icon: LucideIcon
}

const CATEGORY_META: Record<UsefulCategory, CategoryMeta> = {
  prompt: {
    label: 'Промпты',
    itemName: 'промпт',
    cardName: 'Промпт',
    addedText: 'Промпт добавлен',
    emptyTitle: 'Промптов пока нет',
    emptyText: 'Сохраните готовые инструкции для нейросетей, чтобы быстро использовать их в работе.',
    icon: Sparkles,
  },
  website: {
    label: 'Сайты',
    itemName: 'сайт',
    cardName: 'Сайт',
    addedText: 'Сайт добавлен',
    emptyTitle: 'Полезных сайтов пока нет',
    emptyText: 'Сохраните сервисы и инструменты, которыми регулярно пользуетесь.',
    icon: Globe2,
  },
  shop: {
    label: 'Магазины',
    itemName: 'магазин',
    cardName: 'Магазин',
    addedText: 'Магазин добавлен',
    emptyTitle: 'Хороших магазинов пока нет',
    emptyText: 'Добавьте проверенные магазины, каталоги шаблонов и другие места для покупок.',
    icon: ShoppingBag,
  },
  article: {
    label: 'Статьи',
    itemName: 'статью',
    cardName: 'Статья',
    addedText: 'Статья добавлена',
    emptyTitle: 'Сохранённых статей пока нет',
    emptyText: 'Собирайте полезные материалы, инструкции и разборы, к которым хочется вернуться.',
    icon: FileText,
  },
  other: {
    label: 'Другое',
    itemName: 'запись',
    cardName: 'Запись',
    addedText: 'Запись добавлена',
    emptyTitle: 'В этой категории пока пусто',
    emptyText: 'Здесь можно хранить всё полезное, что не подходит под остальные категории.',
    icon: Boxes,
  },
}

const FILTERS: Array<{ id: CategoryFilter; label: string; icon: LucideIcon }> = [
  { id: 'all', label: 'Все', icon: LayoutGrid },
  ...Object.entries(CATEGORY_META).map(([id, meta]) => ({
    id: id as UsefulCategory,
    label: meta.label,
    icon: meta.icon,
  })),
]

function emptyForm(category: UsefulCategory = 'website'): LinkForm {
  return { title: '', category, url: '', description: '' }
}

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
  const [activeCategory, setActiveCategory] = useState<CategoryFilter>('all')
  const [query, setQuery] = useState('')
  const [form, setForm] = useState<LinkForm>(() => emptyForm())
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
        fallback: 'Не удалось загрузить полезные вещи',
      })
      setItems(payload.items)
    } catch (error) {
      setItems(null)
      setFeedback({ kind: 'error', text: messageFrom(error, 'Не удалось загрузить полезные вещи') })
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const counts = useMemo(() => {
    const next: Record<CategoryFilter, number> = {
      all: items?.length ?? 0,
      prompt: 0,
      website: 0,
      shop: 0,
      article: 0,
      other: 0,
    }
    items?.forEach((item) => {
      next[item.category] += 1
    })
    return next
  }, [items])

  const categoryItems = useMemo(
    () => (items ?? []).filter((item) => activeCategory === 'all' || item.category === activeCategory),
    [activeCategory, items],
  )

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    if (!normalized) return categoryItems
    return categoryItems.filter((item) =>
      [
        item.title,
        item.url,
        domainOf(item.url),
        item.description,
        CATEGORY_META[item.category].label,
      ]
        .join(' ')
        .toLocaleLowerCase('ru')
        .includes(normalized),
    )
  }, [categoryItems, query])

  const defaultCreateCategory: UsefulCategory =
    activeCategory === 'all' ? 'website' : activeCategory
  const activeMeta = activeCategory === 'all' ? null : CATEGORY_META[activeCategory]

  const openCreate = () => {
    setEditing(null)
    setForm(emptyForm(defaultCreateCategory))
    setFormError('')
    setFeedback(null)
    setFormOpen(true)
  }

  const openEdit = (item: UsefulLink) => {
    setEditing(item)
    setForm({
      title: item.title,
      category: item.category,
      url: item.url,
      description: item.description,
    })
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
    if (!title) {
      setFormError('Введите название')
      return
    }
    if (form.category === 'prompt' && !description) {
      setFormError('Введите текст промпта')
      return
    }
    if (form.category !== 'prompt' && !url) {
      setFormError('Введите адрес сайта')
      return
    }

    setBusy(true)
    setFormError('')
    try {
      const saved = await apiRequest<UsefulLink>(
        editing ? `/api/useful-links/${editing.id}` : '/api/useful-links',
        {
          method: editing ? 'PUT' : 'POST',
          body: {
            title,
            category: form.category,
            url: form.category === 'prompt' ? '' : url,
            description,
          },
          fallback: editing ? 'Не удалось сохранить изменения' : 'Не удалось добавить запись',
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
        text: editing ? 'Изменения сохранены' : CATEGORY_META[saved.category].addedText,
      })
    } catch (error) {
      setFormError(messageFrom(error, 'Не удалось сохранить запись'))
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
        fallback: 'Не удалось удалить запись',
      })
      setItems((current) => current?.filter((item) => item.id !== deleteTarget.id) ?? [])
      setDeleteTarget(null)
      setFeedback({ kind: 'success', text: 'Запись удалена' })
    } catch (error) {
      setDeleteTarget(null)
      setFeedback({ kind: 'error', text: messageFrom(error, 'Не удалось удалить запись') })
    } finally {
      setBusy(false)
    }
  }

  const copyPrompt = async (item: UsefulLink) => {
    setFeedback(null)
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error('Браузер не разрешил доступ к буферу обмена')
      }
      await navigator.clipboard.writeText(item.description)
      setFeedback({ kind: 'success', text: 'Промпт скопирован' })
    } catch (error) {
      setFeedback({
        kind: 'error',
        text: messageFrom(error, 'Не удалось скопировать промпт'),
      })
    }
  }

  const formMeta = CATEGORY_META[form.category]
  const descriptionLimit = form.category === 'prompt' ? 5000 : 1000
  const formTitle = editing
    ? `Изменить ${formMeta.itemName}`
    : form.category === 'website'
      ? 'Добавить полезный сайт'
      : `Добавить ${formMeta.itemName}`
  const addButtonText = activeMeta
    ? `Добавить ${activeMeta.itemName}`
    : 'Добавить сайт'

  return (
    <div className="data-page useful-things-page">
      <header className="useful-heading">
        <div className="page-title-block">
          <h1>Полезные вещи</h1>
          <p>Промпты, сайты, магазины и статьи — всё нужное для работы в одном каталоге.</p>
        </div>
        <div className="useful-total" aria-label={`Сохранено записей: ${items?.length ?? 0}`}>
          <Bookmark size={18} aria-hidden="true" />
          <strong>{items?.length ?? 0}</strong>
          <span>сохранено</span>
        </div>
      </header>

      <nav className="useful-category-tabs" aria-label="Категории полезных вещей">
        {FILTERS.map(({ id, label, icon: Icon }) => (
          <button
            className={activeCategory === id ? 'is-active' : ''}
            type="button"
            key={id}
            aria-label={`${label}, ${counts[id]}`}
            aria-pressed={activeCategory === id}
            onClick={() => setActiveCategory(id)}
          >
            <Icon size={18} aria-hidden="true" />
            <span>{label}</span>
            <strong>{counts[id]}</strong>
          </button>
        ))}
      </nav>

      <div className="useful-toolbar">
        <label className="useful-search">
          <span className="sr-only">Поиск по полезным вещам</span>
          <Search size={19} aria-hidden="true" />
          <input
            aria-label="Поиск по полезным вещам"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Найти по названию, адресу или содержимому"
          />
          {query && (
            <button type="button" onClick={() => setQuery('')} aria-label="Очистить поиск">
              <X size={16} />
            </button>
          )}
        </label>
        <button className="useful-add-button" type="button" onClick={openCreate}>
          <Plus size={19} />
          {addButtonText}
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
        <section className="useful-state" aria-label="Загрузка полезных вещей">
          <LoaderCircle className="is-spinning" size={30} />
          <h2>Загружаю каталог…</h2>
        </section>
      ) : items !== null && items.length === 0 ? (
        <section className="useful-state">
          <span className="useful-state-icon"><Bookmark size={30} /></span>
          <h2>Здесь будут ваши полезные вещи</h2>
          <p>Добавьте первую запись, чтобы больше не искать рабочие материалы по вкладкам и сообщениям.</p>
          <button type="button" onClick={openCreate}><Plus size={18} />Добавить первую запись</button>
        </section>
      ) : items !== null && categoryItems.length === 0 ? (
        <section className="useful-state">
          <span className={`useful-state-icon category-${activeCategory}`}>
            {activeMeta && <activeMeta.icon size={30} />}
          </span>
          <h2>{activeMeta?.emptyTitle}</h2>
          <p>{activeMeta?.emptyText}</p>
          <button type="button" onClick={openCreate}><Plus size={18} />{addButtonText}</button>
        </section>
      ) : items !== null && filtered.length === 0 ? (
        <section className="useful-state">
          <span className="useful-state-icon"><Search size={30} /></span>
          <h2>По запросу ничего не найдено</h2>
          <p>Попробуйте другое слово или очистите поиск.</p>
          <button type="button" onClick={() => setQuery('')}>Очистить поиск</button>
        </section>
      ) : (
        <section className="useful-grid" aria-label="Сохранённые полезные вещи">
          {filtered.map((item) => {
            const meta = CATEGORY_META[item.category]
            const Icon = meta.icon
            return (
              <article
                className={`useful-card category-${item.category}`}
                key={item.id}
                aria-label={`${meta.cardName} ${item.title}`}
              >
                <header>
                  <span className="useful-card-icon" aria-hidden="true"><Icon size={23} /></span>
                  <div className="useful-card-title">
                    <div>
                      <h2>{item.title}</h2>
                      <span className="useful-category-badge">{meta.label}</span>
                    </div>
                    <span className="useful-card-subtitle">
                      {item.category === 'prompt' ? 'Готов к копированию' : domainOf(item.url)}
                    </span>
                  </div>
                </header>
                <p className={item.category === 'prompt' ? 'is-prompt' : ''}>
                  {item.description || 'Описание пока не добавлено.'}
                </p>
                <footer>
                  {item.category === 'prompt' ? (
                    <button
                      className="useful-open-link useful-copy-button"
                      type="button"
                      onClick={() => void copyPrompt(item)}
                      aria-label={`Копировать ${item.title}`}
                    >
                      <Clipboard size={17} />
                      Копировать
                    </button>
                  ) : (
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
                  )}
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
            )
          })}
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
            <span className={`useful-modal-icon category-${form.category}`}>
              <formMeta.icon size={24} />
            </span>
            <div className="useful-modal-heading">
              <h2 id="useful-form-title">{formTitle}</h2>
              <p>
                {form.category === 'prompt'
                  ? 'Сохраните готовую инструкцию, которую можно копировать одним кликом.'
                  : 'Сохраните полезную ссылку вместе с короткой подсказкой.'}
              </p>
            </div>

            <label className="useful-field">
              <span>Категория</span>
              <select
                aria-label="Категория"
                value={form.category}
                onChange={(event) => {
                  const category = event.target.value as UsefulCategory
                  setForm((current) => ({
                    ...current,
                    category,
                    url: category === 'prompt' ? '' : current.url,
                  }))
                  setFormError('')
                }}
              >
                {Object.entries(CATEGORY_META).map(([id, meta]) => (
                  <option value={id} key={id}>{meta.label}</option>
                ))}
              </select>
            </label>

            <label className="useful-field">
              <span>Название</span>
              <input
                autoFocus
                aria-label="Название"
                maxLength={120}
                value={form.title}
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                placeholder={form.category === 'prompt' ? 'Например, Аудит лендинга' : 'Например, Figma'}
              />
            </label>

            {form.category !== 'prompt' && (
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
            )}

            <label className="useful-field">
              <span>{form.category === 'prompt' ? 'Текст промпта' : 'Описание'}</span>
              <textarea
                aria-label={form.category === 'prompt' ? 'Текст промпта' : 'Описание'}
                maxLength={descriptionLimit}
                rows={form.category === 'prompt' ? 7 : 4}
                value={form.description}
                onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                placeholder={
                  form.category === 'prompt'
                    ? 'Вставьте полный текст промпта'
                    : 'Для чего пригодится эта ссылка'
                }
              />
              <small>{form.description.length}/{descriptionLimit}</small>
            </label>

            {formError && (
              <div className="useful-form-error" role="alert">
                <CircleAlert size={17} />
                {formError}
              </div>
            )}

            <div className="useful-modal-actions">
              <button type="button" onClick={closeForm} disabled={busy}>Отмена</button>
              <button className="is-primary" type="submit" disabled={busy} aria-busy={busy}>
                {busy && <LoaderCircle className="is-spinning" size={17} />}
                {editing ? 'Сохранить изменения' : `Сохранить ${formMeta.itemName}`}
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
            <p>Запись и её содержимое исчезнут из каталога. Это действие нельзя отменить.</p>
            <div className="useful-modal-actions">
              <button type="button" onClick={() => setDeleteTarget(null)} disabled={busy}>Оставить</button>
              <button className="is-danger" type="button" onClick={() => void remove()} disabled={busy}>
                {busy && <LoaderCircle className="is-spinning" size={17} />}
                Удалить {CATEGORY_META[deleteTarget.category].itemName}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
