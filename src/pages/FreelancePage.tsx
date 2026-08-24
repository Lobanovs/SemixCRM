import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  AlertCircle,
  Archive,
  Bot,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  CirclePlay,
  Clock3,
  Eraser,
  ExternalLink,
  Filter,
  Folder,
  LoaderCircle,
  MessageSquare,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  Sparkles,
  UsersRound,
  X,
} from 'lucide-react'
import { EmptyState, MetricCard, SidePanel, StatusBadge, Tag } from '../components/DashboardUi'
import type { UiAccent } from '../components/DashboardUi'
import PageGuide from '../components/PageGuide'
import { FREELANCE_GUIDE } from '../guides'
import { apiRequest } from '../api'
import ProgressiveListFooter from '../components/ProgressiveListFooter'
import {
  BROWSER_SOURCE_KEYS,
  FREELANCE_SOURCE_KEYS,
  FREELANCE_SOURCE_META,
  freelanceSourceLabel,
  isFreelanceSourceKey,
  type FreelanceSourceKey,
} from './freelanceSources'

const sourceKeys = FREELANCE_SOURCE_KEYS
const browserSourceKeys = BROWSER_SOURCE_KEYS
type SourceKey = FreelanceSourceKey
const statuses = ['Новый', 'Написал', 'Откликнулся', 'Ответили', 'Созвон', 'В работе', 'Завершён', 'Отказ']
const accents = Object.fromEntries(sourceKeys.map((source) => [source, FREELANCE_SOURCE_META[source].accent])) as Record<string, string>
accents.manual = 'gray'

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
  relevance_points: number
  relevance_reasons: string[]
  status: string
  next_step: string
  note: string
  archived: boolean
}

type FreelanceStats = { total: number; responded: number; replied: number; in_progress: number; new_today: number; archived: number; stages: Record<string, number> }
type SourceStatus = { source: string; status: string; checked_at?: string; order_count?: number; error?: string; auth_required?: boolean }
type FreelanceSettings = { sources: string[]; keywords: string[]; excluded_keywords: string[]; categories: string[]; min_budget: number; interval_seconds: number; sniper_enabled: boolean; telegram_enabled: boolean }
type SniperStatus = { status: string; sources: Record<string, SourceStatus>; interval_seconds: number }
type FreelanceRun = { id: number; started_at: string; finished_at: string; status: string; inserted_count: number; duplicate_count: number; source_count: number; order_count: number; sources: Record<string, SourceStatus> }
type FreelanceOrdersResponse = { orders: FreelanceOrder[]; stats: FreelanceStats; relevance_max?: number }

const emptyStats: FreelanceStats = { total: 0, responded: 0, replied: 0, in_progress: 0, new_today: 0, archived: 0, stages: {} }
const emptySettings: FreelanceSettings = { sources: [], keywords: [], excluded_keywords: [], categories: [], min_budget: 0, interval_seconds: 60, sniper_enabled: false, telegram_enabled: false }

const sourceLabel = freelanceSourceLabel

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
  const [minRelevance, setMinRelevance] = useState(0)
  const [relevanceMax, setRelevanceMax] = useState(20)
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
  const [showArchived, setShowArchived] = useState(false)
  const [showCleanupModal, setShowCleanupModal] = useState(false)
  const [visibleCount, setVisibleCount] = useState(50)

  const loadData = async (showLoader = false, archivedView = showArchived) => {
    if (showLoader) setLoading(true)
    setError('')
    try {
      const [ordersResponse, settingsResponse, sourceResponse, sniperResponse] = await Promise.all([
        apiRequest<FreelanceOrdersResponse>(`/api/freelance/orders${archivedView ? '?archived=true' : ''}`, { fallback: 'Не удалось загрузить заказы' }),
        apiRequest<FreelanceSettings>('/api/freelance/settings', { fallback: 'Не удалось загрузить настройки' }),
        apiRequest<{ sources: SourceStatus[] }>('/api/freelance/sources', { fallback: 'Не удалось загрузить статусы источников' }),
        apiRequest<SniperStatus>('/api/freelance/sniper/status', { fallback: 'Не удалось загрузить статус снайпера' }),
      ])
      setOrders(ordersResponse.orders ?? [])
      setStats(ordersResponse.stats ?? emptyStats)
      if (ordersResponse.relevance_max) setRelevanceMax(ordersResponse.relevance_max)
      setSettings({ ...settingsResponse, sources: settingsResponse.sources.filter((item) => sourceKeys.includes(item as SourceKey)) })
      setSourceStatuses((sourceResponse.sources ?? []).filter((item) => sourceKeys.includes(item.source as SourceKey)))
      setSniper(sniperResponse)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Не удалось загрузить раздел «Фриланс»')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadData(true, showArchived) }, [showArchived])

  const categories = useMemo(() => ['Все', ...Array.from(new Set(orders.flatMap((order) => [...order.categories, ...order.tags]))).sort((a, b) => a.localeCompare(b, 'ru'))], [orders])
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    const result = orders.filter((order) => {
      const haystack = `${order.title} ${order.description} ${order.customer} ${order.tags.join(' ')} ${order.categories.join(' ')}`.toLocaleLowerCase('ru')
      return (!normalized || haystack.includes(normalized)) && (source === 'Все' || order.source === source) && (status === 'Все' || order.status === status) && (category === 'Все' || order.tags.includes(category) || order.categories.includes(category)) && order.relevance >= minRelevance
    })
    if (sort === 'budget') return [...result].sort((a, b) => (b.budget_max ?? b.budget_min ?? 0) - (a.budget_max ?? a.budget_min ?? 0))
    if (sort === 'newest') return [...result].sort((a, b) => (b.published_at || b.discovered_at).localeCompare(a.published_at || a.discovered_at))
    return [...result].sort((a, b) => b.relevance - a.relevance)
  }, [category, minRelevance, orders, query, sort, source, status])
  useEffect(() => setVisibleCount(50), [filtered])
  const visibleOrders = filtered.slice(0, visibleCount)

  const runAction = async (action: string, request: () => Promise<unknown>, message: string) => {
    setBusy(action)
    setError('')
    try {
      await request()
      setFeedback(message)
      window.setTimeout(() => setFeedback(''), 2200)
      await loadData()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Операция не выполнена')
    } finally {
      setBusy('')
    }
  }

  const updateOrder = (orderId: number, changes: Record<string, unknown>) => runAction(`order-${orderId}`, () => apiRequest(`/api/freelance/orders/${orderId}`, { method: 'PUT', body: changes }), 'Заказ обновлён')
  const toggleSniper = () => runAction('sniper', () => apiRequest(`/api/freelance/sniper/${sniper.status === 'running' ? 'stop' : 'start'}`, { method: 'POST' }), sniper.status === 'running' ? 'Снайпер остановлен' : 'Снайпер запущен')
  const checkNow = () => runAction('check', () => apiRequest('/api/freelance/sniper/check', { method: 'POST' }), 'Проверка источников завершена')
  const archiveOrder = (orderId: number) => runAction(`archive-${orderId}`, () => apiRequest(`/api/freelance/orders/${orderId}`, { method: 'DELETE' }), 'Заказ скрыт')
  const restoreOrder = (orderId: number) => runAction(`restore-${orderId}`, () => apiRequest(`/api/freelance/orders/${orderId}`, { method: 'PUT', body: { archived: false } }), 'Заказ возвращён в активные')
  const openAuth = (source: string) => runAction(`auth-${source}`, () => apiRequest(`/api/freelance/sources/${source}/auth`, { method: 'POST' }), `Окно входа ${sourceLabel(source)} открыто`)
  const openHistory = async () => {
    setShowHistoryModal(true)
    setHistoryLoading(true)
    try {
      const response = await apiRequest<{ runs: FreelanceRun[] }>('/api/freelance/runs', { fallback: 'Не удалось загрузить историю запусков' })
      setRunHistory(response.runs ?? [])
    } catch (historyError) {
      setError(historyError instanceof Error ? historyError.message : 'Не удалось загрузить историю запусков')
    } finally { setHistoryLoading(false) }
  }
  const openRun = async (run: FreelanceRun) => {
    setHistoryLoading(true)
    try {
      const response = await apiRequest<{ orders: FreelanceOrder[] }>(`/api/freelance/runs/${run.id}`, { fallback: 'Не удалось загрузить запуск' })
      setSelectedRun({ run, orders: response.orders ?? [] })
    } catch (historyError) {
      setError(historyError instanceof Error ? historyError.message : 'Не удалось загрузить запуск')
    } finally { setHistoryLoading(false) }
  }

  const addOrder = async (payload: Record<string, unknown>) => {
    await runAction('add-order', () => apiRequest('/api/freelance/orders', { method: 'POST', body: payload }), 'Заказ сохранён')
    setShowOrderModal(false)
  }

  const saveSettings = async (next: FreelanceSettings) => {
    await runAction('settings', () => apiRequest('/api/freelance/settings', { method: 'PUT', body: next }), 'Настройки снайпера сохранены')
    setShowSettingsModal(false)
  }

  const stages = Object.entries(stats.stages).filter(([, value]) => value > 0)
  const sourceErrors = sourceStatuses.filter((item) => sourceKeys.includes(item.source as SourceKey) && (item.status === 'error' || item.status === 'blocked' || item.auth_required))

  return (
    <div className="data-page freelance-page">
      <div className="data-page-grid">
        <section className="data-main-column">
          <header className="page-title-block"><h1>Фриланс</h1><p>Реальные заказы, отклики и приоритетные предложения из выбранных источников.</p></header>

          <PageGuide
            sectionId="freelance"
            title="Как пользоваться разделом «Фриланс»"
            intro="Снайпер сам обходит пять площадок и складывает новые заказы в базу, пока запущен backend."
            steps={FREELANCE_GUIDE}
          />

          <div className="metrics-grid">
            <MetricCard icon={Folder} label="Всего заказов" value={stats.total} hint={stats.new_today ? `+${stats.new_today} сегодня` : 'Только сохранённые заказы'} accent="blue" />
            <MetricCard icon={CirclePlay} label="Откликнулся" value={stats.responded} hint={stats.total ? `${Math.round((stats.responded / stats.total) * 100)}% от всех` : '0% от всех'} accent="green" />
            <MetricCard icon={MessageSquare} label="Ответили" value={stats.replied} hint={stats.total ? `${Math.round((stats.replied / stats.total) * 100)}% от всех` : '0% от всех'} accent="orange" />
            <MetricCard icon={BriefcaseBusiness} label="В работе" value={stats.in_progress} hint={stats.total ? `${Math.round((stats.in_progress / stats.total) * 100)}% от всех` : '0% от всех'} accent="purple" />
          </div>

          <div className="freelance-view-tabs" role="tablist" aria-label="Списки заказов">
            <button className={!showArchived ? 'active' : ''} type="button" role="tab" aria-selected={!showArchived} onClick={() => setShowArchived(false)}><Folder size={17} />Активные <span>{stats.total}</span></button>
            <button className={showArchived ? 'active' : ''} type="button" role="tab" aria-selected={showArchived} onClick={() => setShowArchived(true)}><Archive size={17} />Скрытые <span>{stats.archived}</span></button>
            {showArchived && stats.archived > 0 && <button className="restore-all-tab-action" type="button" disabled={busy === 'restore-all'} onClick={() => void runAction('restore-all', () => apiRequest('/api/freelance/orders/restore-all', { method: 'POST' }), 'Все заказы возвращены в активные')}><RotateCcw size={16} />Вернуть всех</button>}
          </div>

          <div className="toolbar-row freelance-toolbar">
            <label className="local-search"><span className="sr-only">Поиск заказов</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск заказов..." /><Search size={19} /></label>
            <label className="select-control"><span className="sr-only">Статус</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option>Все</option>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="select-control"><span className="sr-only">Источник</span><select value={source} onChange={(event) => setSource(event.target.value)}><option>Все</option>{sourceKeys.map((item) => <option key={item} value={item}>{sourceLabel(item)}</option>)}</select></label>
            <label className="select-control"><span className="sr-only">Категория</span><select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="select-control"><span className="sr-only">Релевантность</span><select value={minRelevance} onChange={(event) => setMinRelevance(Number(event.target.value))}><option value={0}>Любая релевантность</option><option value={40}>От 40% — стоит взглянуть</option><option value={60}>От 60% — профильные</option><option value={80}>От 80% — точно ваши</option></select></label>
            <label className="select-control sort-control"><span className="sr-only">Сортировка</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="relevance">Сначала релевантные</option><option value="newest">Сначала новые</option><option value="budget">Сначала дорогие</option></select></label>
            <button className="solid-action" type="button" onClick={() => setShowOrderModal(true)}><Plus size={19} />Добавить заказ</button>
            <button className="secondary-wide-action" type="button" onClick={() => setShowCleanupModal(true)} disabled={showArchived || !stats.total}><Eraser size={16} />Очистить список</button>
          </div>

          {error && <div className="page-feedback error" role="alert"><AlertCircle size={17} />{error}</div>}
          {feedback && <div className="page-feedback success" role="status"><Check size={17} />{feedback}</div>}
          {loading ? <div className="freelance-loading" role="status"><LoaderCircle className="spin" size={24} />Загружаю сохранённые заказы…</div> : <div className="opportunity-list freelance-list">{filtered.length ? visibleOrders.map((order) => <OrderRow key={order.id} order={order} archived={showArchived} relevanceMax={relevanceMax} busy={busy === `order-${order.id}` || busy === `archive-${order.id}` || busy === `restore-${order.id}`} onUpdate={updateOrder} onArchive={archiveOrder} onRestore={restoreOrder} />) : <EmptyState>{orders.length ? 'По выбранным фильтрам заказы не найдены.' : showArchived ? 'Скрытых заказов нет. Здесь появятся карточки, которые вы убрали из активного списка.' : 'Заказов пока нет. Запустите проверку источников или добавьте заказ вручную.'}</EmptyState>}<ProgressiveListFooter shown={visibleOrders.length} total={filtered.length} step={50} onMore={() => setVisibleCount((count) => Math.min(count + 50, filtered.length))} onAll={() => setVisibleCount(filtered.length)} /></div>}
        </section>

        <aside className="data-side-column">
          <SidePanel className="parser-panel freelance-parser">
            <div className="parser-title"><span className="parser-icon"><Bot size={21} /></span><div><h2>Снайпер заказов</h2><p>Проверяет выбранные площадки локально и добавляет только новые заказы.</p></div></div>
            <div className="source-chip-row">{sourceKeys.map((item) => <ParserSource key={item} source={item} active={settings.sources.includes(item)} status={sourceStatuses.find((statusItem) => statusItem.source === item)} />)}</div>
            <div className="parser-stats"><span>Сохранено<strong>{stats.total}</strong></span><span>Новых сегодня<strong>{stats.new_today} <i /></strong></span></div>
            <div className="parser-filters"><p><Filter />Источники <strong>{settings.sources.length ? settings.sources.map(sourceLabel).join(', ') : 'Не настроены'}</strong></p><p><Search />Ключевые слова <strong>{settings.keywords.join(', ') || 'Не заданы'}</strong></p><p><BriefcaseBusiness />Бюджет от <strong>{settings.min_budget ? `${settings.min_budget.toLocaleString('ru-RU')} ₽` : 'Без ограничения'}</strong></p><p><Clock3 />Интервал <strong>{settings.interval_seconds} сек.</strong></p></div>
            {sourceErrors.length > 0 && <div className="source-error-list" aria-live="polite">{sourceErrors.map((item) => <p key={item.source}><AlertCircle size={14} /><strong>{sourceLabel(item.source)}:</strong> {item.error || 'Требуется авторизация'}</p>)}</div>}
            <button className={`solid-action wide-action ${sniper.status === 'running' ? 'is-running' : ''}`} type="button" onClick={toggleSniper} disabled={busy === 'sniper'}>{busy === 'sniper' ? <LoaderCircle className="spin" size={18} /> : <CirclePlay size={18} />}{sniper.status === 'running' ? 'Остановить снайпер' : 'Запустить снайпер'}</button>
            <button className="secondary-wide-action" type="button" data-guide="freelance-check" onClick={checkNow} disabled={busy === 'check'}>{busy === 'check' ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}Проверить сейчас</button>
            <button className="secondary-wide-action" type="button" data-guide="freelance-settings" onClick={() => setShowSettingsModal(true)}><Settings2 size={16} />Настроить</button>
            <button className="secondary-wide-action" type="button" data-guide="freelance-history" onClick={() => void openHistory()}><Clock3 size={16} />История запусков</button>
          </SidePanel>

          <SidePanel className="recommendations-panel"><h2>Лучшие заказы</h2>{filtered.slice(0, 3).map((order) => <button className="recommendation-item" type="button" key={order.id} onClick={() => setQuery(order.title)}><SourceMark source={order.source} size="small" /><p><strong>{order.title}</strong><span>{formatBudget(order)}</span></p><span><b>{order.relevance}%</b><StatusBadge tone={order.relevance >= 70 ? 'green' : order.relevance >= 40 ? 'orange' : 'gray'}>{order.status}</StatusBadge></span></button>)}{!filtered.length && <p className="empty-panel-copy">Рекомендации появятся после добавления заказов.</p>}</SidePanel>

          <SidePanel className="order-stages-panel"><h2>Этапы заказов</h2>{stages.length ? <div className="order-stage-grid">{stages.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong><i className={label === 'Отказ' ? 'red' : label === 'В работе' ? 'green' : 'blue'} /></div>)}</div> : <p className="empty-panel-copy">Статистика появится после сохранения заказов.</p>}</SidePanel>

          <SidePanel className="nearest-panel freelance-nearest"><h2>Состояние источников</h2>{sourceStatuses.length ? sourceStatuses.map((item) => <SourceState key={item.source} item={item} busy={busy} onAuth={openAuth} onRetry={checkNow} />) : <p className="empty-panel-copy">Проверок источников ещё не было.</p>}</SidePanel>
        </aside>
      </div>

      {showOrderModal && <OrderModal onClose={() => setShowOrderModal(false)} onCreate={addOrder} />}
      {showSettingsModal && <SettingsModal settings={settings} statuses={sourceStatuses} busy={busy === 'settings'} authBusy={busy} onAuth={openAuth} onClose={() => setShowSettingsModal(false)} onSave={saveSettings} />}
      {showCleanupModal && <CleanupModal stats={stats} onClose={() => setShowCleanupModal(false)} onDone={async (archived) => { setShowCleanupModal(false); setFeedback(`Скрыто ${archived} ${plural(archived, 'заказ', 'заказа', 'заказов')}`); window.setTimeout(() => setFeedback(''), 2600); await loadData() }} />}
      {showHistoryModal && <HistoryModal runs={runHistory} selected={selectedRun} loading={historyLoading} onSelect={(run) => void openRun(run)} onClose={() => { setShowHistoryModal(false); setSelectedRun(null) }} />}
    </div>
  )
}

/** Тон и подпись рейтинга: те же пороги, что у карточек клиентов. */
function relevanceTone(relevance: number): UiAccent {
  if (relevance >= 70) return 'green'
  if (relevance >= 40) return 'orange'
  return 'gray'
}

function relevanceLabel(relevance: number) {
  if (relevance >= 70) return 'Профильный'
  if (relevance >= 40) return 'Возможно'
  return 'Не профиль'
}

function SourceMark({ source, size = 'medium' }: { source: string; size?: 'small' | 'medium' | 'large' }) {
  if (!isFreelanceSourceKey(source)) return <span className={`source-mark ${size} manual`}><Folder aria-hidden="true" /></span>
  const meta = FREELANCE_SOURCE_META[source]
  return <span className={`source-mark ${size} ${meta.accent}`}><img src={meta.icon} alt={`${meta.label} — значок источника`} width={192} height={192} /></span>
}

function OrderRow({ order, archived, busy, relevanceMax, onUpdate, onArchive, onRestore }: { order: FreelanceOrder; archived: boolean; busy: boolean; relevanceMax: number; onUpdate: (id: number, changes: Record<string, unknown>) => void; onArchive: (id: number) => void; onRestore: (id: number) => void }) {
  return <article className={`opportunity-row freelance-order-row ${archived ? 'archived-order' : ''}`}><div className="opportunity-identity"><SourceMark source={order.source} size="large" /><div><div className="freelance-order-title"><h2>{order.title}</h2><StatusBadge tone={relevanceTone(order.relevance)}>{relevanceLabel(order.relevance)}</StatusBadge></div><p>{order.description || 'Описание не предоставлено источником.'}</p><div className="tag-row">{[sourceLabel(order.source), ...order.categories, ...order.tags].filter(Boolean).slice(0, 5).map((tag) => <Tag key={tag}>{tag}</Tag>)}</div></div></div><div className="opportunity-meta"><p><BriefcaseBusiness />Бюджет <strong>{formatBudget(order)}</strong></p><p><Sparkles />Источник <strong>{sourceLabel(order.source)}</strong></p><p><Clock3 />Добавлено <strong>{formatDate(order.published_at || order.discovered_at)}</strong></p>{order.customer && <p><UsersRound />Заказчик <strong>{order.customer}</strong></p>}</div><div className="opportunity-status freelance-order-status" data-guide="freelance-status"><div className="order-fit"><div className="order-score-line"><strong>{order.relevance_points}<small>/{relevanceMax}</small></strong><span>{order.relevance}% релевантности</span></div><div className="score-reason-preview">{order.relevance_reasons.slice(0, 2).map((reason) => <span key={reason}><Check size={12} />{reason}</span>)}</div></div><div className="order-status-line"><StatusBadge tone={archived ? 'gray' : order.status === 'Отказ' ? 'red' : order.status === 'В работе' ? 'green' : order.status === 'Ответили' ? 'orange' : 'blue'}>{archived ? 'Скрыт' : order.status}</StatusBadge><label className="status-select-label"><span className="sr-only">Статус заказа {order.title}</span><select value={order.status} onChange={(event) => onUpdate(order.id, { status: event.target.value })} disabled={busy}>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label></div><p className="order-next-step">Следующий шаг: <strong>{order.next_step}</strong></p><div className="stacked-order-actions">{archived ? <button className="restore-row-action" type="button" onClick={() => onRestore(order.id)} disabled={busy}>{busy ? <LoaderCircle className="spin" size={14} /> : <RotateCcw size={14} />}Вернуть в активные</button> : <button className="primary-row-action" type="button" onClick={() => onUpdate(order.id, { status: order.status === 'Новый' ? 'Написал' : order.status })} disabled={busy}>{busy ? <LoaderCircle className="spin" size={14} /> : <ChevronRight size={15} />}Следующий шаг</button>}<button type="button" onClick={() => order.url && window.open(order.url, '_blank', 'noopener,noreferrer')} disabled={!order.url}><span>{order.url ? 'Открыть' : 'Нет ссылки'}</span>{order.url && <ExternalLink size={13} />}</button>{!archived && <button className="danger-row-action" type="button" onClick={() => onArchive(order.id)} disabled={busy}><X size={14} />Скрыть</button>}</div></div></article>
}

function ParserSource({ source, active, status }: { source: SourceKey; active: boolean; status?: SourceStatus }) {
  const meta = FREELANCE_SOURCE_META[source]
  return <span className={`source-chip source-chip-with-mark ${meta.accent} ${active ? 'active' : 'inactive'}`} title={status?.error || (active ? 'Источник включён' : 'Источник выключен')}><SourceMark source={source} size="small" /><span>{meta.label}</span>{status?.auth_required && <AlertCircle size={12} />}</span>
}

function SourceState({ item, busy, onAuth, onRetry }: { item: SourceStatus; busy: string; onAuth: (source: string) => void; onRetry: () => void }) {
  const needsAuth = Boolean(item.auth_required || item.status === 'auth_required')
  const isBlocked = item.status === 'blocked'
  const canAuth = browserSourceKeys.includes(item.source as (typeof browserSourceKeys)[number])
  const label = sourceLabel(item.source)
  const statusLabel = needsAuth ? 'Требуется вход' : isBlocked ? 'Доступ ограничен' : item.status === 'done' ? 'Готово' : item.status === 'empty' ? 'Нет новых' : item.status === 'error' ? 'Ошибка' : item.status
  const tone = item.status === 'done' ? 'green' : needsAuth || isBlocked ? 'orange' : item.status === 'error' ? 'red' : 'gray'
  return <div className={`nearest-action freelance-source-state ${item.status}`}><SourceMark source={item.source} size="medium" /><p><strong>{label}</strong><span>{needsAuth ? 'Войдите в аккаунт и повторите проверку' : item.error || `${item.order_count ?? 0} заказов при последней проверке`}</span></p><StatusBadge tone={tone}>{statusLabel}</StatusBadge>{canAuth && (needsAuth || isBlocked) && <button className="source-auth-button" type="button" aria-label={`Войти в ${label}`} onClick={() => onAuth(item.source)} disabled={busy === `auth-${item.source}`}>{busy === `auth-${item.source}` ? <LoaderCircle className="spin" size={13} /> : <ExternalLink size={13} />}Войти</button>}{item.status === 'error' && <button className="source-auth-button retry" type="button" aria-label={`Повторить проверку ${label}`} onClick={onRetry} disabled={busy === 'check'}>{busy === 'check' ? <LoaderCircle className="spin" size={13} /> : <RotateCcw size={13} />}Повторить</button>}</div>
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
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
    <form className="compact-modal freelance-settings-modal" role="dialog" aria-modal="true" aria-labelledby="freelance-settings-title" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
      <header className="parser-modal-header"><span className="metric-icon blue"><Settings2 /></span><div><h2 id="freelance-settings-title">Настройки снайпера</h2><p className="modal-subtitle">Выберите источники и фильтры для локальной проверки.</p></div><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button></header>
      <div className="parser-modal-body">
        <label>Источники</label>
        <div className="freelance-source-options">{sourceKeys.map((source) => {
          const status = statuses.find((item) => item.source === source)
          const canAuth = browserSourceKeys.includes(source as (typeof browserSourceKeys)[number])
          const needsAuth = Boolean(status?.auth_required || status?.status === 'auth_required' || status?.status === 'blocked')
          const meta = FREELANCE_SOURCE_META[source]
          return <div className={`freelance-source-option ${draft.sources.includes(source) ? 'active' : ''}`} key={source}><label><input type="checkbox" checked={draft.sources.includes(source)} onChange={() => toggleSource(source)} /><SourceMark source={source} size="medium" /><span><strong>{meta.label}</strong><small>{canAuth ? 'Браузерный источник' : 'Публичная лента'}</small></span>{needsAuth && <AlertCircle size={14} />}</label>{canAuth && <button className="source-auth-button" type="button" aria-label={`Войти в ${meta.label}`} onClick={() => onAuth(source)} disabled={authBusy === `auth-${source}`}>{authBusy === `auth-${source}` ? <LoaderCircle className="spin" size={13} /> : <ExternalLink size={13} />}Войти</button>}</div>
        })}</div>
        <label htmlFor="freelance-keywords">Ключевые слова</label><input id="freelance-keywords" value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="React, Next.js, CRM" /><p className="form-hint">Разделяйте слова запятыми.</p>
        <label htmlFor="freelance-excluded">Исключить слова</label><input id="freelance-excluded" value={excluded} onChange={(event) => setExcluded(event.target.value)} placeholder="стажировка, бесплатно" />
        <label htmlFor="freelance-min-budget">Минимальный бюджет, ₽</label><input id="freelance-min-budget" value={draft.min_budget || ''} onChange={(event) => setDraft((current) => ({ ...current, min_budget: Number(event.target.value.replace(/\D/g, '')) || 0 }))} inputMode="numeric" placeholder="Без ограничения" />
        <label htmlFor="freelance-interval">Интервал проверки, секунд</label><input id="freelance-interval" type="number" min={30} max={3600} value={draft.interval_seconds} onChange={(event) => setDraft((current) => ({ ...current, interval_seconds: Number(event.target.value) }))} />
        <label className="switch-field"><input type="checkbox" checked={draft.telegram_enabled} onChange={(event) => setDraft((current) => ({ ...current, telegram_enabled: event.target.checked }))} /><span>Отправлять новые заказы в Telegram</span></label>
        <label className="switch-field"><input type="checkbox" checked={draft.sniper_enabled} onChange={(event) => setDraft((current) => ({ ...current, sniper_enabled: event.target.checked }))} /><span>Запустить снайпер после сохранения</span></label>
      </div>
      <footer className="parser-modal-footer"><button className="solid-action wide-action" type="submit" disabled={busy || !draft.sources.length}>{busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}Сохранить настройки</button></footer>
    </form>
  </div>
}

function HistoryModal({ runs, selected, loading, onSelect, onClose }: { runs: FreelanceRun[]; selected: { run: FreelanceRun; orders: FreelanceOrder[] } | null; loading: boolean; onSelect: (run: FreelanceRun) => void; onClose: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="compact-modal freelance-history-modal" role="dialog" aria-modal="true" aria-labelledby="freelance-history-title" onMouseDown={(event) => event.stopPropagation()}><header className="parser-modal-header"><span className="metric-icon blue"><Clock3 /></span><div><h2 id="freelance-history-title">История запусков</h2><p className="modal-subtitle">Каждый запуск хранит именно те заказы, которые были увидены в тот момент.</p></div><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button></header><div className="freelance-history-body">{loading && <div className="freelance-loading"><LoaderCircle className="spin" size={20} />Загружаю историю…</div>}{!loading && !runs.length && <p className="empty-panel-copy">Запусков ещё не было.</p>}{!loading && runs.length > 0 && <div className="freelance-history-layout"><div className="freelance-run-list">{runs.map((run) => <button className={`freelance-run-item ${selected?.run.id === run.id ? 'active' : ''}`} type="button" key={run.id} onClick={() => onSelect(run)}><strong>Запуск #{run.id}</strong><span>{formatDate(run.started_at)}</span><span>{run.inserted_count} новых · {run.order_count} карточек</span><StatusBadge tone={run.status === 'done' ? 'green' : run.status === 'partial' ? 'orange' : 'red'}>{run.status}</StatusBadge></button>)}</div><div className="freelance-run-detail">{selected ? <><h3>Запуск #{selected.run.id}</h3><p>{formatDate(selected.run.started_at)} · добавлено {selected.run.inserted_count}, дублей {selected.run.duplicate_count}</p>{selected.orders.length ? selected.orders.map((order) => <article key={order.id}><strong>{order.title}</strong><span>{sourceLabel(order.source)} · {formatBudget(order)}</span></article>) : <p className="empty-panel-copy">В этом запуске новых карточек не было.</p>}</> : <p className="empty-panel-copy">Выберите запуск слева.</p>}</div></div>}</div></section></div>
}


/** Склонение существительного по числу: 1 заказ, 2 заказа, 5 заказов. */
function plural(count: number, one: string, few: string, many: string) {
  const mod100 = Math.abs(count) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return many
  if (mod10 === 1) return one
  if (mod10 >= 2 && mod10 <= 4) return few
  return many
}

type CleanupRules = {
  max_relevance: number | null
  older_than_days: number | null
  sources: string[]
  keep_worked: boolean
  include_everything: boolean
}

type CleanupPreview = { matched: number; kept: number; sample: { title: string; relevance: number; source: string }[] }

const emptyRules: CleanupRules = {
  max_relevance: null,
  older_than_days: null,
  sources: [],
  keep_worked: true,
  include_everything: false,
}

/** Готовые сценарии уборки: то, что нужно в 90% случаев, — в один клик. */
const CLEANUP_PRESETS: { id: string; label: string; hint: string; rules: CleanupRules }[] = [
  {
    id: 'irrelevant',
    label: 'Нерелевантные',
    hint: 'Всё ниже 40% — не ваш профиль',
    rules: { ...emptyRules, max_relevance: 40 },
  },
  {
    id: 'stale',
    label: 'Залежавшиеся',
    hint: 'Найдены больше недели назад',
    rules: { ...emptyRules, older_than_days: 7 },
  },
  {
    id: 'stale-irrelevant',
    label: 'Старые и слабые',
    hint: 'Старше 3 дней и ниже 60%',
    rules: { ...emptyRules, older_than_days: 3, max_relevance: 60 },
  },
  {
    id: 'everything',
    label: 'Весь список',
    hint: 'Начать с чистого листа',
    rules: { ...emptyRules, include_everything: true },
  },
]

function CleanupModal({
  stats, onClose, onDone,
}: {
  stats: FreelanceStats
  onClose: () => void
  onDone: (archived: number) => Promise<void>
}) {
  const [rules, setRules] = useState<CleanupRules>({ ...emptyRules, max_relevance: 40 })
  const [preset, setPreset] = useState('irrelevant')
  const [preview, setPreview] = useState<CleanupPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState('')

  const update = (patch: Partial<CleanupRules>) => {
    setPreset('')
    setRules((current) => ({ ...current, ...patch }))
  }

  const applyPreset = (id: string) => {
    const found = CLEANUP_PRESETS.find((item) => item.id === id)
    if (!found) return
    setPreset(id)
    setRules(found.rules)
  }

  // Считаем заранее: скрывать полторы тысячи заказов вслепую — плохая идея.
  useEffect(() => {
    let cancelled = false
    setPreviewing(true)
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          const payload = await apiRequest<CleanupPreview>('/api/freelance/orders/cleanup', {
            method: 'POST', body: { ...rules, preview: true }, fallback: 'Не удалось посчитать',
          })
          if (cancelled) return
          setPreview(payload)
          setError('')
        } catch (previewError) {
          if (!cancelled) setError(previewError instanceof Error ? previewError.message : 'Не удалось посчитать')
        } finally {
          if (!cancelled) setPreviewing(false)
        }
      })()
    }, 250)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [rules])

  const apply = async () => {
    setApplying(true)
    setError('')
    try {
      const payload = await apiRequest<{ archived_count?: number }>('/api/freelance/orders/cleanup', {
        method: 'POST', body: { ...rules, preview: false }, fallback: 'Не удалось скрыть заказы',
      })
      await onDone(payload.archived_count ?? 0)
    } catch (applyError) {
      setError(applyError instanceof Error ? applyError.message : 'Не удалось скрыть заказы')
      setApplying(false)
    }
  }

  const matched = preview?.matched ?? 0
  const nothingSelected = !rules.include_everything && rules.max_relevance === null
    && rules.older_than_days === null && rules.sources.length === 0

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="compact-modal cleanup-modal" role="dialog" aria-modal="true" aria-labelledby="cleanup-title" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button>
        <span className="metric-icon orange"><Eraser /></span>
        <h2 id="cleanup-title">Очистить список заказов</h2>
        <p className="field-hint">Заказы не удаляются, а уходят во вкладку «Скрытые» — оттуда их можно вернуть.</p>

        <span className="field-label">Быстрые сценарии</span>
        <div className="cleanup-presets">
          {CLEANUP_PRESETS.map((item) => (
            <button
              className={preset === item.id ? 'active' : ''}
              type="button"
              key={item.id}
              onClick={() => applyPreset(item.id)}
            >
              <strong>{item.label}</strong>
              <span>{item.hint}</span>
            </button>
          ))}
        </div>

        <label htmlFor="cleanup-relevance">Скрыть с релевантностью ниже</label>
        <select
          id="cleanup-relevance"
          value={rules.max_relevance ?? ''}
          onChange={(event) => update({ max_relevance: event.target.value ? Number(event.target.value) : null })}
        >
          <option value="">Не смотреть на релевантность</option>
          <option value={20}>20%</option>
          <option value={40}>40%</option>
          <option value={60}>60%</option>
          <option value={80}>80%</option>
        </select>

        <label htmlFor="cleanup-age">Скрыть найденные раньше чем</label>
        <select
          id="cleanup-age"
          value={rules.older_than_days ?? ''}
          onChange={(event) => update({ older_than_days: event.target.value ? Number(event.target.value) : null })}
        >
          <option value="">Не смотреть на возраст</option>
          <option value={1}>1 день назад</option>
          <option value={3}>3 дня назад</option>
          <option value={7}>неделю назад</option>
          <option value={14}>две недели назад</option>
          <option value={30}>месяц назад</option>
        </select>

        <span className="field-label">Только эти источники</span>
        <div className="source-toggle-row">
          {sourceKeys.map((item) => (
            <label className="source-toggle" key={item}>
              <input
                type="checkbox"
                checked={rules.sources.includes(item)}
                onChange={() => update({
                  sources: rules.sources.includes(item)
                    ? rules.sources.filter((value) => value !== item)
                    : [...rules.sources, item],
                })}
              />
              {sourceLabel(item)}
            </label>
          ))}
        </div>

        <label className="source-toggle cleanup-safety">
          <input type="checkbox" checked={rules.keep_worked} onChange={(event) => update({ keep_worked: event.target.checked })} />
          Не трогать заказы, с которыми уже работаю
        </label>

        <label className="source-toggle">
          <input type="checkbox" checked={rules.include_everything} onChange={(event) => update({ include_everything: event.target.checked })} />
          Скрыть вообще всё, что подходит под условия
        </label>

        <div className={`cleanup-preview ${matched ? '' : 'is-empty'}`} aria-live="polite">
          {previewing ? <p>Считаю…</p> : nothingSelected ? (
            <p>Выберите сценарий или условие — иначе скрывать нечего.</p>
          ) : (
            <>
              <p><strong>Будет скрыто: {matched}</strong> из {stats.total}. Останется {preview?.kept ?? stats.total}.</p>
              {preview?.sample?.length ? (
                <ul>
                  {preview.sample.map((item) => (
                    <li key={`${item.source}-${item.title}`}><b>{item.relevance}%</b> {item.title}</li>
                  ))}
                </ul>
              ) : null}
            </>
          )}
        </div>

        {error && <p className="field-error" role="alert">{error}</p>}

        <button className="solid-action wide-action" type="button" onClick={() => void apply()} disabled={applying || previewing || !matched}>
          <Eraser size={18} />{applying ? 'Скрываю…' : matched ? `Скрыть ${matched} ${plural(matched, 'заказ', 'заказа', 'заказов')}` : 'Нечего скрывать'}
        </button>
      </section>
    </div>
  )
}
