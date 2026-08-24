import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Archive,
  ArrowLeft,
  Building2,
  CalendarClock,
  CarFront,
  Check,
  CircleCheck,
  Coffee,
  ExternalLink,
  Globe2,
  ListFilter,
  Mail,
  MapPin,
  MessageCircle,
  MessageSquareText,
  Phone,
  PhoneCall,
  Plus,
  RefreshCw,
  Search,
  Scissors,
  Send,
  Sparkles,
  Star,
  Store,
  RotateCcw,
  Trash2,
  UsersRound,
  X,
} from 'lucide-react'
import { EmptyState, MetricCard, SidePanel, StatusBadge, Tag } from '../components/DashboardUi'
import type { UiAccent } from '../components/DashboardUi'
import PageGuide from '../components/PageGuide'
import { CLIENTS_GUIDE } from '../guides'
import ClientMessageModal from './ClientMessageModal'
import ClientRetentionFilters from './ClientRetentionFilters'
import {
  DEFAULT_CLIENT_RETENTION_FILTERS,
  countActiveClientFilters,
  matchesClientRetentionFilters,
} from './clientFilters'
import type { ClientRetentionFilterState } from './clientFilters'
import { apiRequest } from '../api'
import type { LucideIcon } from 'lucide-react'
import ParserControlPanel from './ParserControlPanel'
import ProgressiveListFooter from '../components/ProgressiveListFooter'
import { API_BASE, persistParserSettings, startParserWithSettings } from './parserSettings'
import type { ParserSettings } from './parserSettings'

type ClientStatus = 'Новый' | 'Написал' | 'Ответили' | 'Созвон' | 'КП' | 'Закрыто' | 'Отказ'
type AiMessageStatus = 'ready' | 'stale' | 'missing'
type Contact = { type: string; label: string; value: string; url?: string }

type Client = {
  id: number
  name: string
  category: string
  location: string
  address: string
  source: string
  added: string
  pain: string
  tags: string[]
  status: ClientStatus
  next: string
  match: number
  score: number
  scoreMax: number
  scoreReasons: string[]
  rating: number | null
  reviews: number | null
  phone: string
  website: string
  cardUrl: string
  contacts: Contact[]
  aiMessageStatus: AiMessageStatus
  aiMessageCreatedAt: string
  tone: UiAccent
  icon: LucideIcon
}

const statusOptions: ClientStatus[] = ['Новый', 'Написал', 'Ответили', 'Созвон', 'КП', 'Закрыто', 'Отказ']
const stageOrder = statusOptions
const majorRussianCities = [
  'Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург', 'Казань', 'Нижний Новгород',
  'Красноярск', 'Челябинск', 'Самара', 'Уфа', 'Ростов-на-Дону', 'Краснодар', 'Омск',
  'Воронеж', 'Пермь', 'Волгоград', 'Саратов', 'Тюмень', 'Тольятти', 'Ижевск',
  'Барнаул', 'Ульяновск', 'Иркутск', 'Хабаровск', 'Ярославль', 'Владивосток',
  'Махачкала', 'Томск', 'Оренбург', 'Кемерово', 'Новокузнецк', 'Рязань',
  'Набережные Челны', 'Астрахань', 'Пенза', 'Липецк', 'Киров', 'Чебоксары',
  'Калининград', 'Тула', 'Курск', 'Сочи', 'Ставрополь', 'Улан-Удэ', 'Тверь',
  'Магнитогорск', 'Иваново', 'Брянск', 'Белгород', 'Сургут',
]

const businessNiches = [
  'салоны красоты', 'стоматологии', 'автосервисы', 'юридические услуги', 'медицинские клиники',
  'фитнес-клубы', 'кафе и рестораны', 'кофейни', 'агентства недвижимости', 'строительные компании',
  'ремонт квартир', 'детейлинг', 'барбершопы', 'ветеринарные клиники', 'частные школы',
  'детские центры', 'онлайн-школы', 'магазины мебели', 'гостиницы', 'туристические агентства',
  'бухгалтерские услуги', 'ремонт техники', 'свадебные агентства', 'фотостудии', 'магазины одежды',
  'автошколы', 'косметологии', 'массажные салоны',
]

const toneByStatus: Record<ClientStatus, UiAccent> = {
  Новый: 'blue', Написал: 'orange', Ответили: 'green', Созвон: 'purple',
  КП: 'orange', Закрыто: 'green', Отказ: 'red',
}

type ApiClient = {
  id: number
  name: string
  niche?: string
  category?: string
  city?: string
  address?: string
  source?: string
  created_at?: string
  pain?: string
  tags?: string[]
  status?: string
  next_step?: string
  match_score?: number
  lead_score?: number
  lead_score_max?: number
  lead_score_reasons?: string[]
  rating?: number | null
  reviews?: number | null
  phone?: string
  website?: string
  card_url?: string
  contacts?: Contact[]
  archived?: number
  archived_at?: string
  ai_message_status?: AiMessageStatus
  ai_message_created_at?: string
}

type ParserRun = {
  id: string
  started_at: string
  finished_at?: string
  status: 'running' | 'done' | 'error'
  city: string
  niche: string
  source: string
  limit_count: number
  start_page?: number
  found_count: number
  skipped_count?: number
  parsed_count?: number
  result_count?: number
  snapshot_available?: boolean
  message: string
  error?: string
}
type ParserRunResult = { client_id: number | null; outcome: 'inserted' | 'duplicate'; position: number; created_at: string; snapshot: ApiClient }
type ParserRunDetail = ParserRun & { results: ParserRunResult[] }
type ArchivedClient = Client & { archivedAt: string }
type ApiStats = {
  total: number
  contacted: number
  replied: number
  calls: number
  closed: number
  found_today: number
  new_today: number
  stages: Record<ClientStatus, number>
}

const iconForCategory = (category: string): LucideIcon => {
  const value = category.toLocaleLowerCase('ru')
  if (value.includes('стомат') || value.includes('клиник')) return Building2
  if (value.includes('салон') || value.includes('барбер') || value.includes('космет')) return Scissors
  if (value.includes('авто')) return CarFront
  if (value.includes('коф')) return Coffee
  if (value.includes('юрид')) return UsersRound
  return Store
}

const toClient = (item: ApiClient): Client => {
  const category = item.category || item.niche || 'Бизнес'
  const status = statusOptions.includes(item.status as ClientStatus) ? item.status as ClientStatus : 'Новый'
  return {
    id: Number(item.id), name: item.name, category, location: item.city || '—', address: item.address || '',
    source: item.source || '2GIS', added: item.created_at ? new Date(item.created_at).toLocaleDateString('ru-RU') : 'Сегодня',
    pain: item.pain || 'Нужно уточнить задачи и точки роста бизнеса.', tags: item.tags?.length ? item.tags : ['Новый лид'],
    status, next: item.next_step || 'Написать владельцу', match: Number(item.match_score) || 0,
    score: Number(item.lead_score) || 0, scoreMax: Number(item.lead_score_max) || 23,
    scoreReasons: item.lead_score_reasons || [], rating: item.rating ?? null, reviews: item.reviews ?? null,
    phone: item.phone || '', website: item.website || '', cardUrl: item.card_url || '', contacts: item.contacts || [],
    aiMessageStatus: item.ai_message_status || 'missing', aiMessageCreatedAt: item.ai_message_created_at || '',
    tone: toneByStatus[status], icon: iconForCategory(category),
  }
}
const toArchivedClient = (item: ApiClient): ArchivedClient => ({ ...toClient(item), archivedAt: item.archived_at || '' })

const defaultParserSettings: ParserSettings = { city: 'Москва', niches: ['салоны красоты'], sources: ['2gis'], limit: 0, start_page: 1 }
const emptyStats: ApiStats = {
  total: 0, contacted: 0, replied: 0, calls: 0, closed: 0, found_today: 0, new_today: 0,
  stages: { Новый: 0, Написал: 0, Ответили: 0, Созвон: 0, КП: 0, Закрыто: 0, Отказ: 0 },
}
const sourceLabel = (source: string) => source.split(',').map((item) => {
  const normalized = item.trim().toLowerCase()
  return normalized === '2gis' ? '2GIS' : normalized === 'yandex' ? 'Яндекс Карты' : item.trim()
}).join(', ')
const scoreTone = (score: number): UiAccent => score >= 14 ? 'green' : score >= 8 ? 'orange' : 'blue'
const runCount = (run: ParserRun) => run.parsed_count || (run.found_count || 0) + (run.skipped_count || 0)

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([])
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<'Все' | ClientStatus>('Все')
  const [source, setSource] = useState('Все')
  const [niche, setNiche] = useState('Все')
  const [sort, setSort] = useState('Сначала лучшие лиды')
  const [isParsing, setIsParsing] = useState(false)
  const [isSavingParserSettings, setIsSavingParserSettings] = useState(false)
  const [isParserSettingsReady, setIsParserSettingsReady] = useState(false)
  const [parserMessage, setParserMessage] = useState('')
  const [parserFeedbackKind, setParserFeedbackKind] = useState<'status' | 'error'>('status')
  const [parserSettings, setParserSettings] = useState<ParserSettings>(defaultParserSettings)
  const [savedParserSettings, setSavedParserSettings] = useState<ParserSettings>(defaultParserSettings)
  const [parserRuns, setParserRuns] = useState<ParserRun[]>([])
  const [archivedClients, setArchivedClients] = useState<ArchivedClient[]>([])
  const [pageView, setPageView] = useState<'clients' | 'history' | 'archive'>('clients')
  const [selectedRun, setSelectedRun] = useState<ParserRunDetail | null>(null)
  const [isRunLoading, setIsRunLoading] = useState(false)
  const [isRestoring, setIsRestoring] = useState(false)
  const [showRestoreAllConfirm, setShowRestoreAllConfirm] = useState(false)
  const [apiStats, setApiStats] = useState<ApiStats>(emptyStats)
  const [backendConnected, setBackendConnected] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [selectedClient, setSelectedClient] = useState<Client | null>(null)
  const [aiEnabled, setAiEnabled] = useState(false)
  const [messageClient, setMessageClient] = useState<Client | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<{ kind: 'one'; client: Client } | { kind: 'all' } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [showRetentionFilters, setShowRetentionFilters] = useState(false)
  const [retentionFilters, setRetentionFilters] = useState<ClientRetentionFilterState>({
    ...DEFAULT_CLIENT_RETENTION_FILTERS,
    requiredContacts: [],
  })
  const [visibleClientCount, setVisibleClientCount] = useState(60)

  const refreshBackend = async () => {
    const [clientsResponse, settingsResponse, runsResponse] = await Promise.all([
      fetch(`${API_BASE}/api/clients`), fetch(`${API_BASE}/api/parser/settings`), fetch(`${API_BASE}/api/parser/runs?limit=20`),
    ])
    if (!clientsResponse.ok || !settingsResponse.ok || !runsResponse.ok) throw new Error('Backend CRM недоступен')
    const clientsPayload = await clientsResponse.json() as { clients: ApiClient[]; stats?: ApiStats }
    const settingsPayload = await settingsResponse.json() as ParserSettings
    const runsPayload = await runsResponse.json() as { runs?: ParserRun[] }
    setClients(Array.isArray(clientsPayload.clients) ? clientsPayload.clients.map(toClient) : [])
    setApiStats(clientsPayload.stats || emptyStats)
    setParserSettings(settingsPayload)
    setSavedParserSettings(settingsPayload)
    setIsParserSettingsReady(true)
    setParserRuns(runsPayload.runs || [])
    const archivedResponse = await fetch(`${API_BASE}/api/clients/archived`)
    if (archivedResponse.ok) {
      const archivedPayload = await archivedResponse.json() as { clients?: ApiClient[] }
      setArchivedClients(Array.isArray(archivedPayload.clients) ? archivedPayload.clients.map(toArchivedClient) : [])
    }
    setBackendConnected(true)
  }

  useEffect(() => {
    void refreshBackend().catch(() => {
      setBackendConnected(false)
      setIsParserSettingsReady(false)
      setParserFeedbackKind('error')
      setParserMessage('API недоступен. Запустите проект командой npm run dev — она поднимет frontend и backend вместе.')
    })
  }, [])

  // Без ключа OpenCode кнопка «Написать» не показывается вовсе.
  useEffect(() => {
    void (async () => {
      try {
        const status = await apiRequest<{ enabled: boolean }>('/api/ai/status', { fallback: '' })
        setAiEnabled(Boolean(status.enabled))
      } catch {
        setAiEnabled(false)
      }
    })()
  }, [])

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [pageView])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    const result = clients.filter((client) => {
      const contacts = client.contacts.map((item) => item.value).join(' ')
      const haystack = `${client.name} ${client.category} ${client.location} ${client.address} ${client.source} ${contacts} ${client.tags.join(' ')}`.toLocaleLowerCase('ru')
      return (!normalized || haystack.includes(normalized)) && (status === 'Все' || client.status === status)
        && (source === 'Все' || client.source === source) && (niche === 'Все' || client.category === niche)
        && matchesClientRetentionFilters(client, retentionFilters)
    })
    if (sort === 'Сначала новые') return [...result].sort((a, b) => b.id - a.id)
    if (sort === 'Больше отзывов') return [...result].sort((a, b) => (b.reviews || 0) - (a.reviews || 0))
    return [...result].sort((a, b) => b.score - a.score || b.match - a.match)
  }, [clients, niche, query, retentionFilters, sort, source, status])
  useEffect(() => setVisibleClientCount(60), [filtered])
  const visibleClients = filtered.slice(0, visibleClientCount)
  const sourceOptions = useMemo(() => Array.from(new Set(clients.map((client) => client.source))).sort(), [clients])
  const nicheOptions = useMemo(() => Array.from(new Set(clients.map((client) => client.category))).sort(), [clients])
  const activeRetentionFilterCount = countActiveClientFilters(retentionFilters)
  const emptyClientsMessage = !clients.length
    ? 'Клиентов пока нет. Настройте город и ниши, затем запустите парсер.'
    : activeRetentionFilterCount
      ? 'По выбранным условиям клиентов нет. Ослабьте фильтр «Кто остаётся».'
      : 'По текущим фильтрам клиентов нет. Измените поиск, статус, источник или нишу.'

  const derivedStats = useMemo<ApiStats>(() => {
    const stages = Object.fromEntries(stageOrder.map((stage) => [stage, clients.filter((client) => client.status === stage).length])) as Record<ClientStatus, number>
    return {
      total: clients.length, contacted: clients.length - stages.Новый,
      replied: stages.Ответили + stages.Созвон + stages.КП + stages.Закрыто,
      calls: stages.Созвон, closed: stages.Закрыто, found_today: 0, new_today: 0, stages,
    }
  }, [clients])
  const stats = backendConnected ? apiStats : derivedStats
  const counts = stageOrder.map((stage) => ({ stage, value: stats.stages[stage] || 0 }))

  const updateStatus = async (id: number, next: ClientStatus) => {
    const nextStep = { Новый: 'Написать владельцу', Написал: 'Жду ответа', Ответили: 'Подготовить КП', Созвон: 'Назначить созвон', КП: 'Отправить предложение', Закрыто: 'Запустить проект', Отказ: 'Вернуться позже' }[next]
    setClients((items) => items.map((client) => client.id === id ? { ...client, status: next, next: nextStep, tone: toneByStatus[next] } : client))
    if (!backendConnected) return
    try {
      const response = await fetch(`${API_BASE}/api/clients/${id}/status`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: next, next_step: nextStep }),
      })
      if (!response.ok) throw new Error('Не удалось сохранить статус')
      await refreshBackend()
    } catch (error) {
      setParserMessage(error instanceof Error ? error.message : 'Не удалось сохранить статус')
    }
  }

  const createClient = async (client: Client) => {
    try {
      const response = await fetch(`${API_BASE}/api/clients`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: client.name, category: client.category, city: client.location, source: client.source }),
      })
      if (!response.ok) throw new Error('Не удалось сохранить клиента')
      await refreshBackend()
      setShowModal(false)
    } catch (error) {
      setParserMessage(error instanceof Error ? error.message : 'Не удалось сохранить клиента')
    }
  }

  const saveParserSettings = async () => {
    if (!isParserSettingsReady || isSavingParserSettings || isParsing) return
    setIsSavingParserSettings(true)
    setParserFeedbackKind('status')
    setParserMessage('Сохраняю настройки парсера…')
    try {
      const saved = await persistParserSettings(parserSettings)
      setParserSettings(saved)
      setSavedParserSettings(saved)
      setBackendConnected(true)
      const successMessage = 'Настройки сохранены. Следующий запуск использует новые параметры.'
      setParserMessage(successMessage)
      window.setTimeout(() => setParserMessage((message) => message === successMessage ? '' : message), 4000)
    } catch (error) {
      setParserFeedbackKind('error')
      setParserMessage(error instanceof TypeError ? 'Не удалось подключиться к API. Запустите проект командой npm run dev.' : error instanceof Error ? error.message : 'Не удалось сохранить настройки парсера')
    } finally {
      setIsSavingParserSettings(false)
    }
  }

  const runParser = async () => {
    if (!isParserSettingsReady || isParsing || isSavingParserSettings) return
    setIsParsing(true)
    setParserFeedbackKind('status')
    setParserMessage('Сохраняю настройки перед запуском…')
    try {
      const { jobId } = await startParserWithSettings(parserSettings, {
        onPersist: (saved) => {
          setParserSettings(saved)
          setSavedParserSettings(saved)
          setBackendConnected(true)
          setParserMessage('Настройки сохранены. Запускаю поиск компаний…')
        },
      })
      let finished = false
      while (!finished) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000))
        const statusResponse = await fetch(`${API_BASE}/api/clients/jobs/${jobId}`)
        const payload = await statusResponse.json() as { status?: string; message?: string; error?: string; count?: number; skipped_count?: number }
        setParserMessage(payload.message || 'Парсер работает…')
        if (payload.status === 'done') {
          finished = true
          setParserMessage(`Готово: новых — ${payload.count || 0}, дублей пропущено — ${payload.skipped_count || 0}`)
          await refreshBackend()
        } else if (payload.status === 'error' || payload.status === 'missing') {
          throw new Error(payload.error || payload.message || 'Парсер завершился с ошибкой')
        }
      }
    } catch (error) {
      setParserFeedbackKind('error')
      setParserMessage(error instanceof TypeError ? 'Не удалось подключиться к API. Перезапустите проект командой npm run dev.' : error instanceof Error ? error.message : 'Не удалось связаться с backend')
    } finally {
      setIsParsing(false)
    }
  }

  const deleteClients = async () => {
    if (!deleteTarget || isDeleting) return
    setIsDeleting(true)
    try {
      const endpoint = deleteTarget.kind === 'all' ? `${API_BASE}/api/clients` : `${API_BASE}/api/clients/${deleteTarget.client.id}`
      const response = await fetch(endpoint, { method: 'DELETE' })
      const payload = await response.json() as { detail?: string; archived_count?: number }
      if (!response.ok) throw new Error(payload.detail || 'Не удалось скрыть клиентов')
      setParserMessage(deleteTarget.kind === 'all' ? `Список очищен: скрыто ${payload.archived_count || 0} клиентов` : `${deleteTarget.client.name} скрыт из базы`)
      setDeleteTarget(null)
      setSelectedClient(null)
      await refreshBackend()
    } catch (error) {
      setParserMessage(error instanceof Error ? error.message : 'Не удалось скрыть клиентов')
    } finally {
      setIsDeleting(false)
    }
  }

  const openRun = async (run: ParserRun) => {
    setIsRunLoading(true)
    setParserMessage('')
    try {
      const response = await fetch(`${API_BASE}/api/parser/runs/${encodeURIComponent(run.id)}`)
      const payload = await response.json() as ParserRunDetail & { detail?: string }
      if (!response.ok) throw new Error(payload.detail || 'Не удалось открыть запуск')
      setSelectedRun(payload)
    } catch (error) {
      setParserMessage(error instanceof Error ? error.message : 'Не удалось открыть запуск')
    } finally {
      setIsRunLoading(false)
    }
  }

  const restoreArchived = async (client: ArchivedClient) => {
    setIsRestoring(true)
    try {
      const response = await fetch(`${API_BASE}/api/clients/${client.id}/restore`, { method: 'POST' })
      const payload = await response.json() as ApiClient & { detail?: string }
      if (!response.ok) throw new Error(payload.detail || 'Не удалось восстановить клиента')
      setParserMessage(`Клиент «${client.name}» восстановлен`)
      await refreshBackend()
    } catch (error) {
      setParserMessage(error instanceof Error ? error.message : 'Не удалось восстановить клиента')
    } finally {
      setIsRestoring(false)
    }
  }

  const restoreAllArchived = async () => {
    setIsRestoring(true)
    try {
      const response = await fetch(`${API_BASE}/api/clients/restore-all`, { method: 'POST' })
      const payload = await response.json() as { restored_count?: number; detail?: string }
      if (!response.ok) throw new Error(payload.detail || 'Не удалось восстановить клиентов')
      setShowRestoreAllConfirm(false)
      setParserMessage(`Восстановлено клиентов: ${payload.restored_count || 0}`)
      await refreshBackend()
    } catch (error) {
      setParserMessage(error instanceof Error ? error.message : 'Не удалось восстановить клиентов')
    } finally {
      setIsRestoring(false)
    }
  }

  if (pageView === 'history') return <div className="data-page clients-page"><ParserHistoryView runs={parserRuns} selectedRun={selectedRun} isLoading={isRunLoading} onBack={() => { setSelectedRun(null); setPageView('clients') }} onOpenRun={(run) => void openRun(run)} /></div>
  if (pageView === 'archive') return <div className="data-page clients-page"><ArchiveView clients={archivedClients} isRestoring={isRestoring} onBack={() => setPageView('clients')} onRestore={(client) => void restoreArchived(client)} onRestoreAll={() => setShowRestoreAllConfirm(true)} />{showRestoreAllConfirm && <ConfirmRestoreAllModal isRestoring={isRestoring} onClose={() => setShowRestoreAllConfirm(false)} onConfirm={() => void restoreAllArchived()} />}</div>

  return (
    <div className="data-page clients-page">
      <div className="data-page-grid">
        <section className="data-main-column">
          <header className="page-title-block"><h1>Волк с Уолл-стрит</h1><p>Реальная база бизнесов, отсортированная по очкам лида и готовности к контакту.</p></header>

          <PageGuide
            sectionId="clients"
            title="Как пользоваться разделом «Волк с Уолл-стрит»"
            intro="Парсер собирает карточки компаний из 2GIS, считает очки лида и ведёт их по воронке продаж."
            steps={CLIENTS_GUIDE}
          />

          <div className="metrics-grid">
            <MetricCard icon={Building2} label="Всего клиентов" value={stats.total} hint={`${stats.found_today} найдено сегодня`} accent="blue" />
            <MetricCard icon={Send} label="Написал" value={stats.contacted} hint={stats.total ? `${Math.round(stats.contacted / stats.total * 100)}% от всех` : '0% от всех'} accent="green" />
            <MetricCard icon={MessageCircle} label="Ответили" value={stats.replied} hint={stats.total ? `${Math.round(stats.replied / stats.total * 100)}% от всех` : '0% от всех'} accent="orange" />
            <MetricCard icon={PhoneCall} label="Созвоны" value={stats.calls} hint={stats.total ? `${Math.round(stats.calls / stats.total * 100)}% от всех` : '0% от всех'} accent="purple" />
            <MetricCard icon={CircleCheck} label="Закрыто" value={stats.closed} hint={stats.total ? `${Math.round(stats.closed / stats.total * 100)}% от всех` : '0% от всех'} accent="green" />
          </div>

          <div className="toolbar-row clients-toolbar">
            <label className="local-search"><span className="sr-only">Поиск клиентов</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Название, город или контакт..." /><Search size={19} /></label>
            <label className="select-control"><span className="sr-only">Статус</span><select value={status} onChange={(event) => setStatus(event.target.value as 'Все' | ClientStatus)}><option>Все</option>{statusOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="select-control"><span className="sr-only">Источник</span><select value={source} onChange={(event) => setSource(event.target.value)}><option>Все</option>{sourceOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="select-control"><span className="sr-only">Ниша</span><select value={niche} onChange={(event) => setNiche(event.target.value)}><option>Все</option>{nicheOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="select-control clients-sort"><span className="sr-only">Сортировка</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option>Сначала лучшие лиды</option><option>Больше отзывов</option><option>Сначала новые</option></select></label>
            <button
              className={`toolbar-secondary-action retention-filter-trigger ${activeRetentionFilterCount ? 'active' : ''}`}
              type="button"
              aria-expanded={showRetentionFilters}
              aria-controls="client-retention-filter-panel"
              onClick={() => setShowRetentionFilters((value) => !value)}
            >
              <ListFilter size={18} />Кто остаётся
              {activeRetentionFilterCount > 0 && <span aria-hidden="true">{activeRetentionFilterCount}</span>}
            </button>
            <button className="toolbar-secondary-action" type="button" data-guide="clients-history" onClick={() => setPageView('history')}><CalendarClock size={18} />История</button>
            <button className="toolbar-secondary-action" type="button" data-guide="clients-archive" onClick={() => setPageView('archive')}><Archive size={18} />Скрытые <span>{archivedClients.length}</span></button>
            <button className="solid-action" type="button" onClick={() => setShowModal(true)}><Plus size={18} />Добавить</button>
            <button className="danger-outline-action" type="button" onClick={() => setDeleteTarget({ kind: 'all' })} disabled={!clients.length}><Trash2 size={18} />Очистить</button>
          </div>

          <ClientRetentionFilters
            filters={retentionFilters}
            isOpen={showRetentionFilters}
            totalCount={clients.length}
            visibleCount={filtered.length}
            onChange={setRetentionFilters}
            onClose={() => setShowRetentionFilters(false)}
            onReset={() => setRetentionFilters({ ...DEFAULT_CLIENT_RETENTION_FILTERS, requiredContacts: [] })}
          />

          <div className="client-list">
            {filtered.length ? visibleClients.map((client) => <ClientRow key={client.id} client={client} onStatusChange={updateStatus} onDetails={setSelectedClient} onDelete={(item) => setDeleteTarget({ kind: 'one', client: item })} onWrite={setMessageClient} />) : <EmptyState>{emptyClientsMessage}</EmptyState>}
            <ProgressiveListFooter shown={visibleClients.length} total={filtered.length} step={60} onMore={() => setVisibleClientCount((count) => Math.min(count + 60, filtered.length))} onAll={() => setVisibleClientCount(filtered.length)} />
          </div>
        </section>

        <aside className="data-side-column">
          <SidePanel className="parser-panel clients-parser">
            <ParserControlPanel
              settings={parserSettings}
              savedSettings={savedParserSettings}
              cities={majorRussianCities}
              availableNiches={businessNiches}
              foundToday={stats.found_today}
              newToday={stats.new_today}
              isSaving={isSavingParserSettings}
              isParsing={isParsing}
              isReady={isParserSettingsReady}
              feedback={parserMessage ? { kind: parserFeedbackKind, text: parserMessage } : null}
              onChange={setParserSettings}
              onSave={() => void saveParserSettings()}
              onRun={() => void runParser()}
            />
          </SidePanel>

          <SidePanel className="lead-score-guide"><h2>Как считаются очки</h2><div className="score-guide-list"><span><b>+5</b> нет сайта</span><span><b>+4</b> Telegram, e-mail или WhatsApp</span><span><b>+3</b> больше 30 отзывов</span><span><b>+2</b> рейтинг выше 4,0</span></div><p>Также учитываются телефон, филиалы и ниша с высоким чеком. Максимум — 23 очка.</p></SidePanel>

          <SidePanel className="parser-history-panel"><div className="panel-heading-row"><h2>История запусков</h2><button className="text-link" type="button" onClick={() => setPageView('history')}>Открыть все</button></div>{parserRuns.length ? parserRuns.slice(0, 5).map((run) => <button type="button" className="parser-run-item" key={run.id} onClick={() => { setPageView('history'); void openRun(run) }}><span className={`run-status ${run.status}`} /><p><strong>{sourceLabel(run.source)} · {run.niche}</strong><span>{new Date(run.started_at).toLocaleString('ru-RU')} · стр. {run.start_page || 1} · новых {run.found_count}{run.skipped_count ? ` · дублей ${run.skipped_count}` : ''}</span></p><StatusBadge tone={run.status === 'done' ? 'green' : run.status === 'error' ? 'red' : 'blue'}>{run.status === 'done' ? 'Готово' : run.status === 'error' ? 'Ошибка' : 'В работе'}</StatusBadge></button>) : <p className="empty-panel-copy">Запусков пока нет</p>}</SidePanel>

          <SidePanel className="recommendations-panel clients-recommendations"><h2>Лучшие лиды</h2>{clients.slice().sort((a, b) => b.score - a.score).slice(0, 3).map((client, index) => <button type="button" className="client-recommendation" key={client.id} onClick={() => setSelectedClient(client)}><span className={`recommendation-rank ${index === 0 ? 'purple' : index === 1 ? 'blue' : 'orange'}`}>{index + 1}</span><p><strong>{client.name}</strong><span>{client.score}/{client.scoreMax} очков · {client.reviews || 0} отзывов</span></p><StatusBadge tone={scoreTone(client.score)}>{client.score >= 14 ? 'Горячий' : 'Проверить'}</StatusBadge></button>)}{!clients.length && <p className="empty-panel-copy">Запустите парсер, чтобы увидеть рекомендации</p>}</SidePanel>

          <SidePanel className="client-stages-panel"><h2>Этапы клиентов</h2><div className="client-stage-grid">{counts.map(({ stage, value }) => <div key={stage}><span>{stage}</span><strong>{value}</strong><i className={toneByStatus[stage]} /></div>)}</div></SidePanel>

          <SidePanel className="nearest-panel clients-nearest"><h2>Ближайшие действия</h2>{clients.slice(0, 4).map((client) => <ClientAction key={client.id} icon={client.status === 'Созвон' ? PhoneCall : client.status === 'КП' ? MessageCircle : CalendarClock} title={`${client.next} — ${client.name}`} meta={`${client.location} · ${client.source}`} badge={client.status} tone={toneByStatus[client.status]} />)}{!clients.length && <p className="empty-panel-copy">Добавьте клиентов через парсер</p>}</SidePanel>
        </aside>
      </div>

      {showModal && <ClientModal onClose={() => setShowModal(false)} onCreate={(client) => void createClient(client)} nextId={(clients.length ? Math.max(...clients.map((client) => client.id)) : 0) + 1} />}
      {messageClient && (
        <ClientMessageModal
          clientId={messageClient.id}
          clientName={messageClient.name}
          enabled={aiEnabled}
          onClose={() => setMessageClient(null)}
          onSent={() => updateStatus(messageClient.id, 'Написал')}
          onGenerated={() => setClients((current) => current.map((client) => (
            client.id === messageClient.id
              ? { ...client, aiMessageStatus: 'ready', aiMessageCreatedAt: new Date().toISOString() }
              : client
          )))}
        />
      )}
      {selectedClient && <ClientDetails client={selectedClient} onClose={() => setSelectedClient(null)} />}
      {deleteTarget && <ConfirmDeleteModal target={deleteTarget} isDeleting={isDeleting} onClose={() => setDeleteTarget(null)} onConfirm={() => void deleteClients()} />}
    </div>
  )
}

function ParserHistoryView({ runs, selectedRun, isLoading, onBack, onOpenRun }: { runs: ParserRun[]; selectedRun: ParserRunDetail | null; isLoading: boolean; onBack: () => void; onOpenRun: (run: ParserRun) => void }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Все')
  const [source, setSource] = useState('Все')
  const sources = Array.from(new Set(runs.flatMap((run) => run.source.split(',').map((item) => item.trim())))).filter(Boolean)
  const filtered = runs.filter((run) => {
    const haystack = `${run.city} ${run.niche} ${run.source} ${run.message}`.toLocaleLowerCase('ru')
    return (!query.trim() || haystack.includes(query.trim().toLocaleLowerCase('ru'))) && (status === 'Все' || run.status === status) && (source === 'Все' || run.source.toLocaleLowerCase().includes(source.toLocaleLowerCase()))
  })
  return <div className="history-page-shell">
    <div className="history-page-header"><button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />К клиентам</button><div><p className="eyebrow-label">Wolf workspace</p><h1>История запусков парсера</h1><p>Каждый запуск хранит результат поиска, включая дубли, рейтинги, отзывы и контакты.</p></div></div>
    <div className="history-layout">
      <section className="history-list-card"><div className="history-toolbar"><label className="local-search"><span className="sr-only">Поиск запусков</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Город, ниша или источник" /><Search size={18} /></label><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Статус запуска"><option>Все</option><option value="done">Готово</option><option value="running">В работе</option><option value="error">Ошибка</option></select><select value={source} onChange={(event) => setSource(event.target.value)} aria-label="Источник"> <option>Все</option>{sources.map((item) => <option key={item}>{item}</option>)}</select></div>{filtered.length ? filtered.map((run) => <button type="button" className={`history-run-card ${selectedRun?.id === run.id ? 'selected' : ''}`} key={run.id} onClick={() => onOpenRun(run)}><span className={`run-status ${run.status}`} /><div className="history-run-main"><div className="history-run-title"><strong>{sourceLabel(run.source)}</strong><span>{new Date(run.started_at).toLocaleString('ru-RU')}</span></div><h2>{run.city} · {run.niche}</h2><p>{run.message || 'Запуск парсера'}</p><div className="history-run-meta"><span><b>{runCount(run)}</b> обработано</span><span><b>{run.found_count || 0}</b> новых</span><span><b>{run.skipped_count || 0}</b> дублей</span><span><b>{run.start_page || 1}</b> страница 2GIS</span></div></div><StatusBadge tone={run.status === 'done' ? 'green' : run.status === 'error' ? 'red' : 'blue'}>{run.status === 'done' ? 'Готово' : run.status === 'error' ? 'Ошибка' : 'В работе'}</StatusBadge></button>) : <div className="history-empty"><Archive size={28} /><h2>Запусков не найдено</h2><p>Измените фильтр или запустите парсер ещё раз.</p></div>}</section>
      <section className="history-detail-card">{isLoading ? <div className="history-empty"><Sparkles className="spin" size={25} /><p>Загружаю снимок запуска…</p></div> : selectedRun ? <RunDetailPanel run={selectedRun} /> : <div className="history-empty"><FileClockIcon /><h2>Выберите запуск</h2><p>Нажмите на карточку слева, чтобы увидеть именно найденных клиентов.</p></div>}</section>
    </div>
  </div>
}

function FileClockIcon() { return <CalendarClock size={30} /> }

function RunDetailPanel({ run }: { run: ParserRunDetail }) {
  return <div className="run-detail-content"><div className="run-detail-heading"><div><p className="eyebrow-label">Снимок запуска</p><h2>{run.city} · {run.niche}</h2><p>{sourceLabel(run.source)} · страница 2GIS {run.start_page || 1} · {new Date(run.started_at).toLocaleString('ru-RU')}</p></div><StatusBadge tone={run.status === 'done' ? 'green' : run.status === 'error' ? 'red' : 'blue'}>{run.status === 'done' ? 'Готово' : run.status === 'error' ? 'Ошибка' : 'В работе'}</StatusBadge></div><div className="run-detail-stats"><span><strong>{runCount(run)}</strong>обработано</span><span><strong>{run.found_count || 0}</strong>новых</span><span><strong>{run.skipped_count || 0}</strong>дублей</span></div>{run.snapshot_available ? <div className="run-results-list">{run.results.map((result) => <RunResultCard key={`${run.id}-${result.position}`} result={result} />)}</div> : <div className="legacy-run-notice"><Archive size={22} /><div><strong>Снимок недоступен для этого старого запуска</strong><p>Этот запуск был создан до включения истории результатов. Новые запуски будут хранить каждого клиента, включая дубли.</p></div></div>}</div>
}

function RunResultCard({ result }: { result: ParserRunResult }) {
  const client = toClient(result.snapshot)
  return <article className="run-result-card"><div className="run-result-icon"><Store size={20} /></div><div className="run-result-body"><div className="run-result-title"><h3>{client.name}</h3><span className={`run-outcome ${result.outcome}`}>{result.outcome === 'inserted' ? 'Добавлен' : 'Дубликат'}</span></div><p>{client.category} · {client.location} · {client.source}</p><div className="run-result-proof"><span><Star size={14} fill="currentColor" /> {client.rating ?? '—'}</span><span><MessageSquareText size={14} /> {client.reviews ?? 0} отзывов</span><strong>{client.score}/{client.scoreMax} очков</strong></div><div className="run-result-contacts">{client.contacts.slice(0, 4).map((contact) => <ContactLink contact={contact} key={`${contact.type}-${contact.value}`} />)}{client.cardUrl && <a href={safeHref(client.cardUrl)} target="_blank" rel="noreferrer"><ExternalLink size={14} />Карточка источника</a>}</div></div></article>
}

function ArchiveView({ clients, isRestoring, onBack, onRestore, onRestoreAll }: { clients: ArchivedClient[]; isRestoring: boolean; onBack: () => void; onRestore: (client: ArchivedClient) => void; onRestoreAll: () => void }) {
  const [query, setQuery] = useState('')
  const [visibleCount, setVisibleCount] = useState(60)
  const filtered = clients.filter((client) => `${client.name} ${client.category} ${client.location} ${client.source}`.toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru')))
  useEffect(() => setVisibleCount(60), [clients, query])
  const visibleClients = filtered.slice(0, visibleCount)
  return <div className="archive-page-shell"><div className="archive-page-header"><button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />К клиентам</button><div><p className="eyebrow-label">Архив базы</p><h1>Скрытые клиенты</h1><p>Очистка только убирает клиентов из рабочего списка. Здесь их можно вернуть без повторного парсинга.</p></div><button className="solid-action" type="button" onClick={onRestoreAll} disabled={!clients.length || isRestoring}><RotateCcw size={17} />Восстановить всех</button></div><div className="archive-toolbar"><label className="local-search"><span className="sr-only">Поиск скрытых клиентов</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по архиву" /><Search size={18} /></label><span className="archive-count">{clients.length} в архиве</span></div>{filtered.length ? <><div className="archive-client-grid">{visibleClients.map((client) => <ArchiveClientCard client={client} isRestoring={isRestoring} onRestore={onRestore} key={client.id} />)}</div><ProgressiveListFooter shown={visibleClients.length} total={filtered.length} step={60} onMore={() => setVisibleCount((count) => Math.min(count + 60, filtered.length))} onAll={() => setVisibleCount(filtered.length)} /></> : <EmptyState>{clients.length ? 'По этому запросу клиентов нет.' : 'Архив пуст. Скрытые клиенты появятся здесь после очистки списка.'}</EmptyState>}</div>
}

function ArchiveClientCard({ client, isRestoring, onRestore }: { client: ArchivedClient; isRestoring: boolean; onRestore: (client: ArchivedClient) => void }) {
  const Icon = client.icon
  return <article className="archive-client-card"><div className="archive-card-top"><span className={`client-logo ${client.tone}`}><Icon size={21} /></span><span className="archived-badge">Скрыт {client.archivedAt ? new Date(client.archivedAt).toLocaleDateString('ru-RU') : ''}</span></div><h2>{client.name}</h2><p>{client.category} · {client.location}</p><div className="client-proof"><span><Star size={14} fill="currentColor" />{client.rating ?? '—'}</span><span><MessageSquareText size={14} />{client.reviews ?? 0} отзывов</span><strong>{client.score}/{client.scoreMax} очков</strong></div><div className="archive-card-links">{client.cardUrl && <a href={safeHref(client.cardUrl)} target="_blank" rel="noreferrer"><ExternalLink size={14} />Источник</a>}{client.contacts.slice(0, 2).map((contact) => <ContactLink contact={contact} key={`${contact.type}-${contact.value}`} />)}</div><button className="secondary-wide-action" type="button" onClick={() => onRestore(client)} disabled={isRestoring}><RotateCcw size={16} />Восстановить</button></article>
}

function ConfirmRestoreAllModal({ isRestoring, onClose, onConfirm }: { isRestoring: boolean; onClose: () => void; onConfirm: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="compact-modal confirm-delete-modal restore-confirm-modal" role="alertdialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><span className="metric-icon blue"><RotateCcw size={23} /></span><h2>Восстановить всех клиентов?</h2><p>Все скрытые записи снова появятся в рабочем списке. История запусков останется без изменений.</p><div className="confirm-actions"><button type="button" onClick={onClose} disabled={isRestoring}>Отмена</button><button className="solid-action" type="button" onClick={onConfirm} disabled={isRestoring}>{isRestoring ? 'Восстанавливаю…' : 'Восстановить всех'}</button></div></section></div>
}

function ClientRow({ client, onStatusChange, onDetails, onDelete, onWrite }: { client: Client; onStatusChange: (id: number, status: ClientStatus) => void; onDetails: (client: Client) => void; onDelete: (client: Client) => void; onWrite: (client: Client) => void }) {
  const Icon = client.icon
  const visibleContacts = client.contacts.filter((item) => item.type !== 'website').slice(0, 4)
  const aiMeta = client.aiMessageStatus === 'ready'
    ? { label: 'Текст готов', note: 'Можно открыть и отправить', icon: CircleCheck }
    : client.aiMessageStatus === 'stale'
      ? { label: 'Нужно обновить', note: 'Данные клиента изменились', icon: RefreshCw }
      : { label: 'Текст не создан', note: 'Генерация ещё не запускалась', icon: Sparkles }
  const AiStatusIcon = aiMeta.icon
  return <article className="client-row">
    <div className="client-identity"><span className={`client-logo ${client.tone}`}><Icon size={24} /></span><div><h2>{client.name}</h2><p className="client-category">{client.category}</p><p className="client-source"><MapPin size={13} />{client.location}<span>·</span>{client.source}<span>·</span>{client.added}</p><div className="client-proof"><span><Star size={14} fill="currentColor" />{client.rating ?? '—'}</span><span><MessageSquareText size={14} />{client.reviews ?? 0} отзывов</span></div><div className="tag-row">{client.tags.slice(0, 4).map((tag) => <Tag key={tag}>{tag}</Tag>)}</div></div></div>
    <div className="client-pain"><p>{client.pain}</p><div className="client-contact-list">{visibleContacts.map((contact) => <ContactLink contact={contact} key={`${contact.type}-${contact.value}`} />)}{!visibleContacts.length && <span className="no-direct-contact">Нет Telegram, e-mail или WhatsApp</span>}</div></div>
    <div className="client-status-column"><StatusBadge tone={toneByStatus[client.status]}>{client.status}</StatusBadge><span>Следующий шаг</span><strong>{client.next}</strong><select aria-label={`Статус клиента ${client.name}`} value={client.status} onChange={(event) => onStatusChange(client.id, event.target.value as ClientStatus)}>{statusOptions.map((item) => <option key={item}>{item}</option>)}</select></div>
    <div className="client-fit">
      <div className="client-score-line" data-guide="clients-score"><StatusBadge tone={scoreTone(client.score)}>{client.score >= 14 ? 'Горячий лид' : client.score >= 8 ? 'Перспективный' : 'Нужно проверить'}</StatusBadge><strong>{client.score}<small>/{client.scoreMax}</small></strong></div>
      <small>{client.match}% релевантности</small>
      <div className="score-reason-preview">{client.scoreReasons.slice(0, 2).map((reason) => <span key={reason}><Check size={12} />{reason}</span>)}</div>
      <div className="client-actions">
        <div className={`client-ai-summary ${client.aiMessageStatus}`}>
          <AiStatusIcon size={17} />
          <span><strong>{aiMeta.label}</strong><small>{aiMeta.note}</small></span>
        </div>
        <button type="button" onClick={() => onDetails(client)}>Подробнее</button>
        {client.cardUrl ? <a href={safeHref(client.cardUrl)} target="_blank" rel="noreferrer">Источник <ExternalLink size={13} /></a> : <button type="button" disabled>Нет источника</button>}
        {client.website ? <a className="client-website-action" href={safeHref(client.website)} target="_blank" rel="noreferrer"><Globe2 size={14} />Сайт</a> : <button type="button" disabled><Globe2 size={14} />Сайт не найден</button>}
        <button className="client-delete-action" type="button" onClick={() => onDelete(client)} aria-label={`Скрыть клиента ${client.name}`}><Trash2 size={14} />Скрыть</button>
        <button className="client-ai-action" type="button" data-guide="clients-write" aria-label={`Посмотреть текст для ${client.name}`} onClick={() => onWrite(client)}><Sparkles size={14} />Посмотреть текст</button>
        <button className="primary-row-action" type="button" data-guide="clients-status" onClick={() => onStatusChange(client.id, client.status === 'Новый' ? 'Написал' : client.status)}>Изменить статус</button>
      </div>
    </div>
  </article>
}

function ContactLink({ contact }: { contact: Contact }) {
  const Icon = contact.type === 'phone' ? Phone : contact.type === 'email' ? Mail : contact.type === 'website' ? Globe2 : MessageCircle
  return <a href={contactHref(contact)} target={contact.type === 'phone' || contact.type === 'email' ? undefined : '_blank'} rel="noreferrer" title={contact.value}><Icon size={14} /><span>{contact.label}</span></a>
}

function safeHref(value: string) { return /^https?:\/\//i.test(value) ? value : `https://${value}` }
function contactHref(contact: Contact) {
  if (contact.type === 'phone') return `tel:${contact.value.replace(/[^\d+]/g, '')}`
  if (contact.type === 'email') return `mailto:${contact.value.replace(/^mailto:/i, '')}`
  return safeHref(contact.url || contact.value)
}

function ClientAction({ icon: Icon, title, meta, badge, tone }: { icon: LucideIcon; title: string; meta: string; badge: string; tone: UiAccent }) { return <div className="nearest-action"><Icon className={tone} size={24} /><p><strong>{title}</strong><span>{meta}</span></p><StatusBadge tone={tone}>{badge}</StatusBadge></div> }

function ClientModal({ onClose, onCreate, nextId }: { onClose: () => void; onCreate: (client: Client) => void; nextId: number }) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState(businessNiches[0])
  const [city, setCity] = useState('Москва')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return
    onCreate({ id: nextId, name: name.trim(), category, location: city, address: '', source: 'Добавлен вручную', added: 'Сегодня', pain: 'Нужно уточнить задачи и точки роста бизнеса.', tags: ['Новый лид'], status: 'Новый', next: 'Найти контакт', match: 0, score: 3, scoreMax: 23, scoreReasons: ['Ниша с высоким чеком +3'], rating: null, reviews: null, phone: '', website: '', cardUrl: '', contacts: [], aiMessageStatus: 'missing', aiMessageCreatedAt: '', tone: 'blue', icon: Building2 })
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal client-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className="metric-icon blue"><Building2 /></span><h2>Новый клиент</h2><label htmlFor="client-name">Название бизнеса</label><input id="client-name" autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Например, Studio Forma" /><label htmlFor="client-category">Ниша</label><select id="client-category" value={category} onChange={(event) => setCategory(event.target.value)}>{businessNiches.map((item) => <option key={item}>{item}</option>)}</select><label htmlFor="client-city">Город</label><select id="client-city" value={city} onChange={(event) => setCity(event.target.value)}>{majorRussianCities.map((item) => <option key={item}>{item}</option>)}</select><button className="solid-action wide-action" type="submit" disabled={!name.trim()}><Plus size={18} />Сохранить клиента</button></form></div>
}

function ClientDetails({ client, onClose }: { client: Client; onClose: () => void }) {
  const Icon = client.icon
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="compact-modal client-details-modal" role="dialog" aria-modal="true" aria-labelledby="client-details-title" onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className={`metric-icon ${client.tone}`}><Icon /></span><h2 id="client-details-title">{client.name}</h2><p className="modal-subtitle">{client.category} · {client.location} · {client.source}</p><div className="details-grid"><span>Очки лида<strong>{client.score}/{client.scoreMax}</strong></span><span>Рейтинг<strong>{client.rating ?? '—'} · {client.reviews ?? 0} отзывов</strong></span><span>Статус<strong>{client.status}</strong></span><span>Следующий шаг<strong>{client.next}</strong></span></div><div className="details-score-reasons">{client.scoreReasons.map((reason) => <span key={reason}><Check size={14} />{reason}</span>)}</div><p className="details-pain">{client.pain}</p><div className="details-contact-list">{client.contacts.map((contact) => <ContactLink contact={contact} key={`${contact.type}-${contact.value}`} />)}{!client.contacts.length && <span>Контакты в источнике не указаны</span>}</div><div className="tag-row">{client.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div>{client.cardUrl && <a className="solid-action wide-action" href={safeHref(client.cardUrl)} target="_blank" rel="noreferrer">Открыть карточку в источнике <ExternalLink size={17} /></a>}</section></div>
}

function ConfirmDeleteModal({ target, isDeleting, onClose, onConfirm }: { target: { kind: 'one'; client: Client } | { kind: 'all' }; isDeleting: boolean; onClose: () => void; onConfirm: () => void }) {
  const isAll = target.kind === 'all'
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="compact-modal confirm-delete-modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" onMouseDown={(event) => event.stopPropagation()}><span className="delete-modal-icon"><Trash2 size={23} /></span><h2 id="delete-title">{isAll ? 'Очистить список клиентов?' : `Скрыть «${target.client.name}»?`}</h2><p>{isAll ? 'Все видимые клиенты исчезнут из рабочего списка. При повторном парсинге они не добавятся снова как дубли.' : 'Клиент исчезнет из рабочего списка и не вернётся после повторного запуска парсера.'}</p><div className="confirm-actions"><button type="button" onClick={onClose} disabled={isDeleting}>Отмена</button><button className="danger-solid-action" type="button" onClick={onConfirm} disabled={isDeleting}>{isDeleting ? 'Скрываю…' : isAll ? 'Очистить список' : 'Скрыть клиента'}</button></div></section></div>
}
