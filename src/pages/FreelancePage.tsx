import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  AlertCircle,
  Bot,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  CirclePlay,
  Clock3,
  ExternalLink,
  FileCode2,
  Filter,
  Folder,
  Globe2,
  LoaderCircle,
  MessageSquare,
  PanelsTopLeft,
  Plus,
  Search,
  Send,
  Settings2,
  Sparkles,
  UsersRound,
  X,
} from 'lucide-react'
import { EmptyState, MetricCard, SidePanel, StatusBadge, Tag } from '../components/DashboardUi'
import type { UiAccent } from '../components/DashboardUi'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const sourceKeys = ['kwork', 'fl', 'freelance_ru', 'workzilla', 'freelancehunt', 'profi', 'youdo'] as const
const browserSourceKeys = ['workzilla', 'profi', 'youdo'] as const
type SourceKey = (typeof sourceKeys)[number]
const statuses = ['Новый', 'Написал', 'Откликнулся', 'Ответили', 'Созвон', 'В работе', 'Завершён', 'Отказ']
const accents: Record<string, UiAccent> = { kwork: 'green', fl: 'blue', freelance_ru: 'purple', workzilla: 'cyan', freelancehunt: 'orange', profi: 'pink', youdo: 'blue', manual: 'gray' }
const icons: Record<string, typeof Send> = { kwork: Send, fl: BriefcaseBusiness, freelance_ru: PanelsTopLeft, workzilla: Bot, freelancehunt: FileCode2, profi: UsersRound, youdo: Globe2, manual: Folder }

type FreelanceOrder = {
  id: number
  source: string
  external_id: string
  title: string
  description: string
  url: string
  customer: string
  categories: string[]
  tags: string[]
  budget_min: number | null
  budget_max: number | null
  currency: string
  budget_text: string
  published_at: string
  discovered_at: string
  relevance: number
  relevance_reasons: string[]
  status: string
  next_step: string
  note: string
  archived: boolean
}

type FreelanceStats = { total: number; responded: number; replied: number; in_progress: number; new_today: number; stages: Record<string, number> }
type SourceStatus = { source: string; status: string; checked_at?: string; order_count?: number; error?: string; auth_required?: boolean }
type FreelanceSettings = { sources: string[]; keywords: string[]; excluded_keywords: string[]; categories: string[]; min_budget: number; interval_seconds: number; sniper_enabled: boolean; telegram_enabled: boolean }
type SniperStatus = { status: string; sources: Record<string, SourceStatus>; interval_seconds: number }
type FreelanceRun = { id: number; started_at: string; finished_at: string; status: string; inserted_count: number; duplicate_count: number; source_count: number; order_count: number; sources: Record<string, SourceStatus> }

const emptyStats: FreelanceStats = { total: 0, responded: 0, replied: 0, in_progress: 0, new_today: 0, stages: {} }
const emptySettings: FreelanceSettings = { sources: [], keywords: [], excluded_keywords: [], categories: [], min_budget: 0, interval_seconds: 60, sniper_enabled: false, telegram_enabled: false }

function sourceLabel(source: string) {
  return ({ kwork: 'Kwork', fl: 'FL.ru', freelance_ru: 'Freelance.ru', workzilla: 'Workzilla', freelancehunt: 'Freelancehunt', profi: 'Profi.ru', youdo: 'YouDo', manual: 'Вручную' } as Record<string, string>)[source] ?? source
}

function formatBudget(order: FreelanceOrder) {
  if (order.budget_text) return order.budget_text
  if (order.budget_min == null && order.budget_max == null) return 'Не указан'
  const format = (value: number | null) => value == null ? '' : `${value.toLocaleString('ru-RU')} ${order.currency === 'RUB' ? '₽' : order.currency}`
  return order.budget_min != null && order.budget_max != null ? `${format(order.budget_min)} – ${format(order.budget_max)}` : format(order.budget_max ?? order.budget_min)
}

function formatDate(value: string) {
  if (!value) return 'Дата не указана'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function FreelancePage() {
  const [orders, setOrders] = useState<FreelanceOrder[]>([])
  const [stats, setStats] = useState<FreelanceStats>(emptyStats)
  const [sourceStatuses, setSourceStatuses] = useState<SourceStatus[]>([])
  const [settings, setSettings] = useState<FreelanceSettings>(emptySettings)
  const [sniper, setSniper] = useState<SniperStatus>({ status: 'stopped', sources: {}, interval_seconds: 60 })
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('Все')
  const [status, setStatus] = useState('Все')
  const [category, setCategory] = useState('Все')
  const [sort, setSort] = useState('relevance')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')
  const [showOrderModal, setShowOrderModal] = useState(false)
  const [showSettingsModal, setShowSettingsModal] = useState(false)
  const [showHistoryModal, setShowHistoryModal] = useState(false)
  const [runHistory, setRunHistory] = useState<FreelanceRun[]>([])
  const [selectedRun, setSelectedRun] = useState<{ run: FreelanceRun; orders: FreelanceOrder[] } | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)

  const loadData = async (showLoader = false) => {
    if (showLoader) setLoading(true)
    setError('')
    try {
      const [ordersResponse, settingsResponse, sourceResponse, sniperResponse] = await Promise.all([
        fetch(`${API_BASE}/api/freelance/orders`),
        fetch(`${API_BASE}/api/freelance/settings`),
        fetch(`${API_BASE}/api/freelance/sources`),
        fetch(`${API_BASE}/api/freelance/sniper/status`),
      ])
      if (![ordersResponse, settingsResponse, sourceResponse, sniperResponse].every((response) => response.ok)) throw new Error('Не удалось загрузить данные фриланса')
      const orderData = await ordersResponse.json()
      setOrders(orderData.orders ?? [])
      setStats(orderData.stats ?? emptyStats)
      setSettings(await settingsResponse.json())
      setSourceStatuses((await sourceResponse.json()).sources ?? [])
      setSniper(await sniperResponse.json())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Не удалось загрузить раздел «Фриланс»')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadData(true) }, [])

  const categories = useMemo(() => ['Все', ...Array.from(new Set(orders.flatMap((order) => [...order.categories, ...order.tags]))).sort((a, b) => a.localeCompare(b, 'ru'))], [orders])
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    const result = orders.filter((order) => {
      const haystack = `${order.title} ${order.description} ${order.customer} ${order.tags.join(' ')} ${order.categories.join(' ')}`.toLocaleLowerCase('ru')
      return (!normalized || haystack.includes(normalized)) && (source === 'Все' || order.source === source) && (status === 'Все' || order.status === status) && (category === 'Все' || order.tags.includes(category) || order.categories.includes(category))
    })
    if (sort === 'budget') return [...result].sort((a, b) => (b.budget_max ?? b.budget_min ?? 0) - (a.budget_max ?? a.budget_min ?? 0))
    if (sort === 'newest') return [...result].sort((a, b) => (b.published_at || b.discovered_at).localeCompare(a.published_at || a.discovered_at))
    return [...result].sort((a, b) => b.relevance - a.relevance)
  }, [category, orders, query, sort, source, status])

  const runAction = async (action: string, request: () => Promise<Response>, message: string) => {
    setBusy(action)
    setError('')
    try {
      const response = await request()
      if (!response.ok) throw new Error((await response.json()).detail ?? 'Операция не выполнена')
      setFeedback(message)
      window.setTimeout(() => setFeedback(''), 2200)
      await loadData()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Операция не выполнена')
    } finally {
      setBusy('')
    }
  }

  const updateOrder = (orderId: number, changes: Record<string, unknown>) => runAction(`order-${orderId}`, () => fetch(`${API_BASE}/api/freelance/orders/${orderId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes) }), 'Заказ обновлён')
  const toggleSniper = () => runAction('sniper', () => fetch(`${API_BASE}/api/freelance/sniper/${sniper.status === 'running' ? 'stop' : 'start'}`, { method: 'POST' }), sniper.status === 'running' ? 'Снайпер остановлен' : 'Снайпер запущен')
  const checkNow = () => runAction('check', () => fetch(`${API_BASE}/api/freelance/sniper/check`, { method: 'POST' }), 'Проверка источников завершена')
  const archiveOrder = (orderId: number) => runAction(`archive-${orderId}`, () => fetch(`${API_BASE}/api/freelance/orders/${orderId}`, { method: 'DELETE' }), 'Заказ скрыт')
  const openAuth = (source: string) => runAction(`auth-${source}`, () => fetch(`${API_BASE}/api/freelance/sources/${source}/auth`, { method: 'POST' }), `Окно входа ${sourceLabel(source)} открыто`)
  const openHistory = async () => {
    setShowHistoryModal(true)
    setHistoryLoading(true)
    try {
      const response = await fetch(`${API_BASE}/api/freelance/runs`)
      if (!response.ok) throw new Error('Не удалось загрузить историю запусков')
      setRunHistory((await response.json()).runs ?? [])
    } catch (historyError) {
      setError(historyError instanceof Error ? historyError.message : 'Не удалось загрузить историю запусков')
    } finally { setHistoryLoading(false) }
  }
  const openRun = async (run: FreelanceRun) => {
    setHistoryLoading(true)
    try {
      const response = await fetch(`${API_BASE}/api/freelance/runs/${run.id}`)
      if (!response.ok) throw new Error('Не удалось загрузить запуск')
      setSelectedRun({ run, orders: (await response.json()).orders ?? [] })
    } catch (historyError) {
      setError(historyError instanceof Error ? historyError.message : 'Не удалось загрузить запуск')
    } finally { setHistoryLoading(false) }
  }

  const addOrder = async (payload: Record<string, unknown>) => {
    await runAction('add-order', () => fetch(`${API_BASE}/api/freelance/orders`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }), 'Заказ сохранён')
    setShowOrderModal(false)
  }

  const saveSettings = async (next: FreelanceSettings) => {
    await runAction('settings', () => fetch(`${API_BASE}/api/freelance/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(next) }), 'Настройки снайпера сохранены')
    setShowSettingsModal(false)
  }

  const stages = Object.entries(stats.stages).filter(([, value]) => value > 0)
  const sourceErrors = sourceStatuses.filter((item) => item.status === 'error' || item.auth_required)

  return (
    <div className="data-page freelance-page">
      <div className="data-page-grid">
        <section className="data-main-column">
          <header className="page-title-block"><h1>Фриланс</h1><p>Реальные заказы, отклики и приоритетные предложения из выбранных источников.</p></header>

          <div className="metrics-grid">
            <MetricCard icon={Folder} label="Всего заказов" value={stats.total} hint={stats.new_today ? `+${stats.new_today} сегодня` : 'Только сохранённые заказы'} accent="blue" />
            <MetricCard icon={CirclePlay} label="Откликнулся" value={stats.responded} hint={stats.total ? `${Math.round((stats.responded / stats.total) * 100)}% от всех` : '0% от всех'} accent="green" />
            <MetricCard icon={MessageSquare} label="Ответили" value={stats.replied} hint={stats.total ? `${Math.round((stats.replied / stats.total) * 100)}% от всех` : '0% от всех'} accent="orange" />
            <MetricCard icon={BriefcaseBusiness} label="В работе" value={stats.in_progress} hint={stats.total ? `${Math.round((stats.in_progress / stats.total) * 100)}% от всех` : '0% от всех'} accent="purple" />
          </div>

          <div className="toolbar-row freelance-toolbar">
            <label className="local-search"><span className="sr-only">Поиск заказов</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск заказов..." /><Search size={19} /></label>
            <label className="select-control"><span className="sr-only">Статус</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option>Все</option>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="select-control"><span className="sr-only">Источник</span><select value={source} onChange={(event) => setSource(event.target.value)}><option>Все</option>{sourceKeys.map((item) => <option key={item} value={item}>{sourceLabel(item)}</option>)}</select></label>
            <label className="select-control"><span className="sr-only">Категория</span><select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="select-control sort-control"><span className="sr-only">Сортировка</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="relevance">Сначала релевантные</option><option value="newest">Сначала новые</option><option value="budget">Сначала дорогие</option></select></label>
            <button className="solid-action" type="button" onClick={() => setShowOrderModal(true)}><Plus size={19} />Добавить заказ</button>
          </div>

          {error && <div className="page-feedback error" role="alert"><AlertCircle size={17} />{error}</div>}
          {feedback && <div className="page-feedback success" role="status"><Check size={17} />{feedback}</div>}
          {loading ? <div className="freelance-loading" role="status"><LoaderCircle className="spin" size={24} />Загружаю сохранённые заказы…</div> : <div className="opportunity-list freelance-list">{filtered.length ? filtered.map((order) => <OrderRow key={order.id} order={order} busy={busy === `order-${order.id}` || busy === `archive-${order.id}`} onUpdate={updateOrder} onArchive={archiveOrder} />) : <EmptyState>{orders.length ? 'По выбранным фильтрам заказы не найдены.' : 'Заказов пока нет. Запустите проверку источников или добавьте заказ вручную.'}</EmptyState>}</div>}
        </section>

        <aside className="data-side-column">
          <SidePanel className="parser-panel freelance-parser">
            <div className="parser-title"><span className="parser-icon"><Bot size={21} /></span><div><h2>Снайпер заказов</h2><p>Проверяет выбранные площадки локально и добавляет только новые заказы.</p></div></div>
            <div className="source-chip-row">{sourceKeys.map((item) => <ParserSource key={item} text={sourceLabel(item)} tone={accents[item]} active={settings.sources.includes(item)} status={sourceStatuses.find((statusItem) => statusItem.source === item)} />)}</div>
            <div className="parser-stats"><span>Сохранено<strong>{stats.total}</strong></span><span>Новых сегодня<strong>{stats.new_today} <i /></strong></span></div>
            <div className="parser-filters"><p><Filter />Источники <strong>{settings.sources.length ? settings.sources.map(sourceLabel).join(', ') : 'Не настроены'}</strong></p><p><Search />Ключевые слова <strong>{settings.keywords.join(', ') || 'Не заданы'}</strong></p><p><BriefcaseBusiness />Бюджет от <strong>{settings.min_budget ? `${settings.min_budget.toLocaleString('ru-RU')} ₽` : 'Без ограничения'}</strong></p><p><Clock3 />Интервал <strong>{settings.interval_seconds} сек.</strong></p></div>
            {sourceErrors.length > 0 && <div className="source-error-list">{sourceErrors.map((item) => <p key={item.source}><AlertCircle size={14} /><strong>{sourceLabel(item.source)}:</strong> {item.error || 'Требуется авторизация'}</p>)}</div>}
            <button className={`solid-action wide-action ${sniper.status === 'running' ? 'is-running' : ''}`} type="button" onClick={toggleSniper} disabled={busy === 'sniper'}>{busy === 'sniper' ? <LoaderCircle className="spin" size={18} /> : <CirclePlay size={18} />}{sniper.status === 'running' ? 'Остановить снайпер' : 'Запустить снайпер'}</button>
            <button className="secondary-wide-action" type="button" onClick={checkNow} disabled={busy === 'check'}>{busy === 'check' ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}Проверить сейчас</button>
            <button className="secondary-wide-action" type="button" onClick={() => setShowSettingsModal(true)}><Settings2 size={16} />Настроить</button>
            <button className="secondary-wide-action" type="button" onClick={() => void openHistory()}><Clock3 size={16} />История запусков</button>
          </SidePanel>

          <SidePanel className="recommendations-panel"><h2>Лучшие заказы</h2>{filtered.slice(0, 3).map((order) => <button className="recommendation-item" type="button" key={order.id} onClick={() => setQuery(order.title)}><span className={`mini-order-icon ${accents[order.source] ?? 'blue'}`}><SourceIcon source={order.source} /></span><p><strong>{order.title}</strong><span>{formatBudget(order)}</span></p><span><b>{order.relevance}%</b><StatusBadge tone={order.relevance >= 70 ? 'green' : order.relevance >= 40 ? 'orange' : 'gray'}>{order.status}</StatusBadge></span></button>)}{!filtered.length && <p className="empty-panel-copy">Рекомендации появятся после добавления заказов.</p>}</SidePanel>

          <SidePanel className="order-stages-panel"><h2>Этапы заказов</h2>{stages.length ? <div className="order-stage-grid">{stages.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong><i className={label === 'Отказ' ? 'red' : label === 'В работе' ? 'green' : 'blue'} /></div>)}</div> : <p className="empty-panel-copy">Статистика появится после сохранения заказов.</p>}</SidePanel>

          <SidePanel className="nearest-panel freelance-nearest"><h2>Состояние источников</h2>{sourceStatuses.length ? sourceStatuses.map((item) => <div className="nearest-action" key={item.source}><span className={`source-health-dot ${item.status}`} /><p><strong>{sourceLabel(item.source)}</strong><span>{item.auth_required ? 'Требуется вход' : item.error || `${item.order_count ?? 0} заказов при последней проверке`}</span></p><StatusBadge tone={item.status === 'done' ? 'green' : item.auth_required ? 'orange' : item.status === 'error' ? 'red' : 'gray'}>{item.auth_required ? 'Вход' : item.status === 'done' ? 'Готово' : item.status}</StatusBadge>{item.auth_required && browserSourceKeys.includes(item.source as (typeof browserSourceKeys)[number]) && <button className="source-auth-button" type="button" onClick={() => openAuth(item.source)} disabled={busy === `auth-${item.source}`}>{busy === `auth-${item.source}` ? <LoaderCircle className="spin" size={13} /> : <ExternalLink size={13} />}Открыть вход</button>}</div>) : <p className="empty-panel-copy">Проверок источников ещё не было.</p>}</SidePanel>
        </aside>
      </div>

      {showOrderModal && <OrderModal onClose={() => setShowOrderModal(false)} onCreate={addOrder} />}
      {showSettingsModal && <SettingsModal settings={settings} statuses={sourceStatuses} busy={busy === 'settings'} authBusy={busy} onAuth={openAuth} onClose={() => setShowSettingsModal(false)} onSave={saveSettings} />}
      {showHistoryModal && <HistoryModal runs={runHistory} selected={selectedRun} loading={historyLoading} onSelect={(run) => void openRun(run)} onClose={() => { setShowHistoryModal(false); setSelectedRun(null) }} />}
    </div>
  )
}

function SourceIcon({ source }: { source: string }) {
  const Icon = icons[source] ?? Folder
  return <Icon size={20} />
}

function OrderRow({ order, busy, onUpdate, onArchive }: { order: FreelanceOrder; busy: boolean; onUpdate: (id: number, changes: Record<string, unknown>) => void; onArchive: (id: number) => void }) {
  const accent = accents[order.source] ?? 'blue'
  return <article className="opportunity-row freelance-order-row"><div className="opportunity-identity"><span className={`project-logo ${accent}`}><SourceIcon source={order.source} /></span><div><div className="freelance-order-title"><h2>{order.title}</h2><StatusBadge tone={order.relevance >= 70 ? 'green' : order.relevance >= 40 ? 'orange' : 'gray'}>{order.relevance}% match</StatusBadge></div><p>{order.description || 'Описание не предоставлено источником.'}</p><div className="tag-row">{[sourceLabel(order.source), ...order.categories, ...order.tags].filter(Boolean).slice(0, 5).map((tag) => <Tag key={tag}>{tag}</Tag>)}</div></div></div><div className="opportunity-meta"><p><BriefcaseBusiness />Бюджет <strong>{formatBudget(order)}</strong></p><p><Sparkles />Источник <strong>{sourceLabel(order.source)}</strong></p><p><Clock3 />Добавлено <strong>{formatDate(order.published_at || order.discovered_at)}</strong></p>{order.customer && <p><UsersRound />Заказчик <strong>{order.customer}</strong></p>}</div><div className="opportunity-status freelance-order-status"><StatusBadge tone={order.status === 'Отказ' ? 'red' : order.status === 'В работе' ? 'green' : order.status === 'Ответили' ? 'orange' : 'blue'}>{order.status}</StatusBadge><span>Следующий шаг</span><strong>{order.next_step}</strong><label className="status-select-label"><span className="sr-only">Статус заказа {order.title}</span><select value={order.status} onChange={(event) => onUpdate(order.id, { status: event.target.value })} disabled={busy}>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label><div className="stacked-order-actions"><button type="button" onClick={() => order.url && window.open(order.url, '_blank', 'noopener,noreferrer')} disabled={!order.url}><span>{order.url ? 'Открыть источник' : 'Ссылка отсутствует'}</span>{order.url && <ExternalLink size={14} />}</button><button className="primary-row-action" type="button" onClick={() => onUpdate(order.id, { status: order.status === 'Новый' ? 'Написал' : order.status })} disabled={busy}>{busy ? <LoaderCircle className="spin" size={14} /> : <ChevronRight size={15} />}Следующий шаг</button><button className="danger-row-action" type="button" onClick={() => onArchive(order.id)} disabled={busy}><X size={14} />Скрыть</button></div></div></article>
}

function ParserSource({ text, tone, active, status }: { text: string; tone: UiAccent; active: boolean; status?: SourceStatus }) {
  return <span className={`source-chip ${tone} ${active ? 'active' : 'inactive'}`} title={status?.error || (active ? 'Источник включён' : 'Источник выключен')}><i>{text.slice(0, 2)}</i>{text}{status?.auth_required && <AlertCircle size={12} />}</span>
}

function OrderModal({ onClose, onCreate }: { onClose: () => void; onCreate: (payload: Record<string, unknown>) => Promise<void> }) {
  const [title, setTitle] = useState('')
  const [source, setSource] = useState<SourceKey | 'manual'>('manual')
  const [url, setUrl] = useState('')
  const [budget, setBudget] = useState('')
  const [description, setDescription] = useState('')
  const submit = (event: FormEvent) => { event.preventDefault(); void onCreate({ source, title: title.trim(), url: url.trim(), description: description.trim(), budget_min: budget ? Number(budget) : null, budget_text: budget ? `${Number(budget).toLocaleString('ru-RU')} ₽` : '' }) }
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal freelance-order-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className="metric-icon purple"><BriefcaseBusiness /></span><h2>Новый заказ</h2><label htmlFor="freelance-order-title">Название заказа</label><input id="freelance-order-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, CRM для клиники" required /><label htmlFor="freelance-order-source">Источник</label><select id="freelance-order-source" value={source} onChange={(event) => setSource(event.target.value as SourceKey | 'manual')}><option value="manual">Добавлен вручную</option>{sourceKeys.map((item) => <option key={item} value={item}>{sourceLabel(item)}</option>)}</select><label htmlFor="freelance-order-url">Ссылка на заказ</label><input id="freelance-order-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://" type="url" /><label htmlFor="freelance-order-budget">Бюджет от, ₽</label><input id="freelance-order-budget" value={budget} onChange={(event) => setBudget(event.target.value.replace(/\D/g, ''))} placeholder="50000" inputMode="numeric" /><label htmlFor="freelance-order-description">Описание</label><textarea id="freelance-order-description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Что нужно сделать" rows={3} /><button className="solid-action wide-action" type="submit" disabled={!title.trim()}><Plus size={18} />Сохранить заказ</button></form></div>
}

function SettingsModal({ settings, statuses, busy, authBusy, onAuth, onClose, onSave }: { settings: FreelanceSettings; statuses: SourceStatus[]; busy: boolean; authBusy: string; onAuth: (source: string) => void; onClose: () => void; onSave: (settings: FreelanceSettings) => Promise<void> }) {
  const [draft, setDraft] = useState(settings)
  const [keywords, setKeywords] = useState(settings.keywords.join(', '))
  const [excluded, setExcluded] = useState(settings.excluded_keywords.join(', '))
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave({ ...draft, keywords: keywords.split(',').map((item) => item.trim()).filter(Boolean), excluded_keywords: excluded.split(',').map((item) => item.trim()).filter(Boolean), min_budget: Number(draft.min_budget) || 0, interval_seconds: Math.max(30, Number(draft.interval_seconds) || 60) }) }
  const toggleSource = (source: string) => setDraft((current) => ({ ...current, sources: current.sources.includes(source) ? current.sources.filter((item) => item !== source) : [...current.sources, source] }))
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal freelance-settings-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}><header className="parser-modal-header"><span className="metric-icon blue"><Settings2 /></span><div><h2>Настройки снайпера</h2><p className="modal-subtitle">Выберите источники и фильтры для локальной проверки.</p></div><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button></header><div className="parser-modal-body"><label>Источники</label><div className="freelance-source-options">{sourceKeys.map((source) => { const status = statuses.find((item) => item.source === source); const canAuth = browserSourceKeys.includes(source as (typeof browserSourceKeys)[number]); return <div className={`freelance-source-option ${draft.sources.includes(source) ? 'active' : ''}`} key={source}><label><input type="checkbox" checked={draft.sources.includes(source)} onChange={() => toggleSource(source)} /><span>{sourceLabel(source)}</span>{status?.auth_required && <AlertCircle size={14} />}</label>{canAuth && <button className="source-auth-button" type="button" onClick={() => onAuth(source)} disabled={authBusy === `auth-${source}`}>{authBusy === `auth-${source}` ? <LoaderCircle className="spin" size={13} /> : <ExternalLink size={13} />}Открыть вход</button>}</div> })}</div><label htmlFor="freelance-keywords">Ключевые слова</label><input id="freelance-keywords" value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="React, Next.js, CRM" /><p className="form-hint">Разделяйте слова запятыми.</p><label htmlFor="freelance-excluded">Исключить слова</label><input id="freelance-excluded" value={excluded} onChange={(event) => setExcluded(event.target.value)} placeholder="стажировка, бесплатно" /><label htmlFor="freelance-min-budget">Минимальный бюджет, ₽</label><input id="freelance-min-budget" value={draft.min_budget || ''} onChange={(event) => setDraft((current) => ({ ...current, min_budget: Number(event.target.value.replace(/\D/g, '')) || 0 }))} inputMode="numeric" placeholder="Без ограничения" /><label htmlFor="freelance-interval">Интервал проверки, секунд</label><input id="freelance-interval" type="number" min={30} max={3600} value={draft.interval_seconds} onChange={(event) => setDraft((current) => ({ ...current, interval_seconds: Number(event.target.value) }))} /><label className="switch-field"><input type="checkbox" checked={draft.telegram_enabled} onChange={(event) => setDraft((current) => ({ ...current, telegram_enabled: event.target.checked }))} /><span>Отправлять новые заказы в Telegram</span></label><label className="switch-field"><input type="checkbox" checked={draft.sniper_enabled} onChange={(event) => setDraft((current) => ({ ...current, sniper_enabled: event.target.checked }))} /><span>Запустить снайпер после сохранения</span></label></div><footer className="parser-modal-footer"><button className="solid-action wide-action" type="submit" disabled={busy || !draft.sources.length}>{busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}Сохранить настройки</button></footer></form></div>
}

function HistoryModal({ runs, selected, loading, onSelect, onClose }: { runs: FreelanceRun[]; selected: { run: FreelanceRun; orders: FreelanceOrder[] } | null; loading: boolean; onSelect: (run: FreelanceRun) => void; onClose: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="compact-modal freelance-history-modal" role="dialog" aria-modal="true" aria-labelledby="freelance-history-title" onMouseDown={(event) => event.stopPropagation()}><header className="parser-modal-header"><span className="metric-icon blue"><Clock3 /></span><div><h2 id="freelance-history-title">История запусков</h2><p className="modal-subtitle">Каждый запуск хранит именно те заказы, которые были увидены в тот момент.</p></div><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button></header><div className="freelance-history-body">{loading && <div className="freelance-loading"><LoaderCircle className="spin" size={20} />Загружаю историю…</div>}{!loading && !runs.length && <p className="empty-panel-copy">Запусков ещё не было.</p>}{!loading && runs.length > 0 && <div className="freelance-history-layout"><div className="freelance-run-list">{runs.map((run) => <button className={`freelance-run-item ${selected?.run.id === run.id ? 'active' : ''}`} type="button" key={run.id} onClick={() => onSelect(run)}><strong>Запуск #{run.id}</strong><span>{formatDate(run.started_at)}</span><span>{run.inserted_count} новых · {run.order_count} карточек</span><StatusBadge tone={run.status === 'done' ? 'green' : run.status === 'partial' ? 'orange' : 'red'}>{run.status}</StatusBadge></button>)}</div><div className="freelance-run-detail">{selected ? <><h3>Запуск #{selected.run.id}</h3><p>{formatDate(selected.run.started_at)} · добавлено {selected.run.inserted_count}, дублей {selected.run.duplicate_count}</p>{selected.orders.length ? selected.orders.map((order) => <article key={order.id}><strong>{order.title}</strong><span>{sourceLabel(order.source)} · {formatBudget(order)}</span></article>) : <p className="empty-panel-copy">В этом запуске новых карточек не было.</p>}</> : <p className="empty-panel-copy">Выберите запуск слева.</p>}</div></div>}</div></section></div>
}
