import { useEffect, useMemo, useState } from 'react'
import {
  Building2,
  CalendarClock,
  CarFront,
  Check,
  CircleCheck,
  Coffee,
  ExternalLink,
  Globe2,
  MapPin,
  MessageCircle,
  PawPrint,
  PhoneCall,
  Plus,
  Search,
  Scissors,
  Send,
  Settings2,
  Sparkles,
  Store,
  UsersRound,
  X,
} from 'lucide-react'
import { EmptyState, MetricCard, SidePanel, StatusBadge, Tag } from '../components/DashboardUi'
import type { UiAccent } from '../components/DashboardUi'
import type { LucideIcon } from 'lucide-react'

type ClientStatus = 'Новый' | 'Написал' | 'Ответили' | 'Созвон' | 'КП' | 'Закрыто' | 'Отказ'

type Client = {
  id: number
  name: string
  category: string
  location: string
  source: string
  added: string
  pain: string
  tags: string[]
  status: ClientStatus
  next: string
  match: number
  tone: UiAccent
  icon: LucideIcon
}

const statusOptions: ClientStatus[] = ['Новый', 'Написал', 'Ответили', 'Созвон', 'КП', 'Закрыто', 'Отказ']

const initialClients: Client[] = [
  { id: 1, name: 'Стоматология Улыбка', category: 'Стоматология', location: 'Москва', source: '2GIS', added: '20.05.2026', pain: 'Боль: устаревший сайт, нет онлайн-записи и системы учёта лидов.', tags: ['Сайт', 'CRM', 'Лиды', 'Автоматизация'], status: 'Новый', next: 'Написать владельцу', match: 92, tone: 'purple', icon: Building2 },
  { id: 2, name: 'Салон красоты LIME', category: 'Салон красоты', location: 'Санкт-Петербург', source: 'Яндекс Карты', added: '18.05.2026', pain: 'Боль: запись только по телефону, много пропущенных заявок.', tags: ['Сайт', 'WhatsApp', 'Онлайн-запись', 'Чат-бот'], status: 'Написал', next: 'Жду ответа', match: 86, tone: 'green', icon: Scissors },
  { id: 3, name: 'Автосервис DrivePro', category: 'Автосервис', location: 'Москва', source: '2GIS', added: '17.05.2026', pain: 'Боль: нет базы клиентов и напоминаний о ТО, теряются повторные обращения.', tags: ['CRM', 'Автоматизация', 'Напоминания', 'Лиды'], status: 'Ответили', next: 'Подготовить КП', match: 78, tone: 'blue', icon: CarFront },
  { id: 4, name: 'Юридический центр Партнёр', category: 'Юридические услуги', location: 'Санкт-Петербург', source: 'Яндекс Карты', added: '16.05.2026', pain: 'Боль: слабый сайт, нет квизов и AI-ассистента для первичных консультаций.', tags: ['Лендинг', 'AI агент', 'Чат-бот', 'CRM'], status: 'Созвон', next: 'Созвон завтра 14:00', match: 74, tone: 'orange', icon: UsersRound },
  { id: 5, name: 'Кофейня Daily Cup', category: 'Кофейня', location: 'Москва', source: '2GIS', added: '15.05.2026', pain: 'Боль: нет программы лояльности и базы постоянных гостей.', tags: ['Чат-бот', 'Лояльность', 'Мини-CRM', 'Автоматизация'], status: 'Закрыто', next: 'Запуск проекта', match: 88, tone: 'orange', icon: Coffee },
  { id: 6, name: 'Студия ремонта Forma', category: 'Ремонт квартир', location: 'Казань', source: 'Google Maps', added: '14.05.2026', pain: 'Боль: заявки теряются между мессенджерами и менеджерами.', tags: ['Сайт', 'CRM', 'Telegram'], status: 'КП', next: 'Отправить предложение', match: 71, tone: 'cyan', icon: Store },
]

const toneByStatus: Record<ClientStatus, UiAccent> = {
  Новый: 'blue',
  Написал: 'orange',
  Ответили: 'green',
  Созвон: 'purple',
  КП: 'orange',
  Закрыто: 'green',
  Отказ: 'red',
}

const stageOrder: ClientStatus[] = ['Новый', 'Написал', 'Ответили', 'Созвон', 'КП', 'Закрыто', 'Отказ']

const iconForCategory = (category: string): LucideIcon => {
  if (category.includes('Стомат')) return Building2
  if (category.includes('Салон') || category.includes('Барбер')) return Scissors
  if (category.includes('Авто')) return CarFront
  if (category.includes('Коф')) return Coffee
  return Store
}

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>(() => {
    try {
      const stored = window.localStorage.getItem('semix-crm-clients')
      if (!stored) return initialClients
      const parsed = JSON.parse(stored) as Array<Omit<Client, 'icon'>>
      return parsed.map((client) => ({ ...client, icon: iconForCategory(client.category) }))
    } catch {
      return initialClients
    }
  })
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<'Все' | ClientStatus>('Все')
  const [source, setSource] = useState('Все')
  const [niche, setNiche] = useState('Все')
  const [sort, setSort] = useState('Сначала релевантные')
  const [isParsing, setIsParsing] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [selectedClient, setSelectedClient] = useState<Client | null>(null)

  useEffect(() => {
    const serializable = clients.map(({ icon: _icon, ...client }) => client)
    window.localStorage.setItem('semix-crm-clients', JSON.stringify(serializable))
  }, [clients])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    const result = clients.filter((client) => {
      const haystack = `${client.name} ${client.category} ${client.location} ${client.source} ${client.tags.join(' ')}`.toLocaleLowerCase('ru')
      return (!normalized || haystack.includes(normalized)) && (status === 'Все' || client.status === status) && (source === 'Все' || client.source === source) && (niche === 'Все' || client.category === niche)
    })
    if (sort === 'Сначала новые') return [...result].sort((a, b) => b.id - a.id)
    return [...result].sort((a, b) => b.match - a.match)
  }, [clients, niche, query, sort, source, status])

  const counts = useMemo(() => stageOrder.map((stage) => ({ stage, value: clients.filter((client) => client.status === stage).length })), [clients])
  const contacted = clients.filter((client) => client.status !== 'Новый').length
  const replied = clients.filter((client) => ['Ответили', 'Созвон', 'КП', 'Закрыто'].includes(client.status)).length
  const calls = clients.filter((client) => client.status === 'Созвон').length
  const closed = clients.filter((client) => client.status === 'Закрыто').length

  const updateStatus = (id: number, next: ClientStatus) => setClients((items) => items.map((client) => client.id === id ? { ...client, status: next, tone: toneByStatus[next] } : client))

  const runParser = () => {
    if (isParsing) return
    setIsParsing(true)
    window.setTimeout(() => {
      setClients((items) => [...items, { id: 7, name: 'Клиника Nova', category: 'Стоматология', location: 'Москва', source: '2GIS', added: 'Сегодня', pain: 'Боль: нет современной страницы услуг и записи через сайт.', tags: ['Сайт', 'CRM', 'Онлайн-запись'], status: 'Новый', next: 'Написать владельцу', match: 84, tone: 'purple', icon: Building2 }, { id: 8, name: 'Барбершоп North', category: 'Барбершоп', location: 'Санкт-Петербург', source: 'Яндекс Карты', added: 'Сегодня', pain: 'Боль: заявки приходят в разные чаты, нет единой базы клиентов.', tags: ['CRM', 'Telegram', 'Чат-бот'], status: 'Новый', next: 'Найти контакт', match: 76, tone: 'green', icon: Scissors }])
      setIsParsing(false)
    }, 850)
  }

  return (
    <div className="data-page clients-page">
      <div className="data-page-grid">
        <section className="data-main-column">
          <header className="page-title-block"><h1>Волк с Уолл-стрит</h1><p>База бизнесов для аутрича: сайты, CRM, AI-агенты и автоматизация.</p></header>

          <div className="metrics-grid">
            <MetricCard icon={Building2} label="Всего клиентов" value={clients.length} hint="+32 за неделю" accent="blue" />
            <MetricCard icon={Send} label="Написал" value={contacted} hint="27% от всех" accent="green" />
            <MetricCard icon={MessageCircle} label="Ответили" value={replied} hint="9% от всех" accent="orange" />
            <MetricCard icon={PhoneCall} label="Созвоны" value={calls} hint="4% от всех" accent="purple" />
            <MetricCard icon={CircleCheck} label="Закрыто" value={closed} hint="1% от всех" accent="green" />
          </div>

          <div className="toolbar-row clients-toolbar">
            <label className="local-search"><span className="sr-only">Поиск клиентов</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск клиентов..." /><Search size={19} /></label>
            <label className="select-control"><span className="sr-only">Статус</span><select value={status} onChange={(event) => setStatus(event.target.value as 'Все' | ClientStatus)}><option>Все</option>{statusOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="select-control"><span className="sr-only">Источник</span><select value={source} onChange={(event) => setSource(event.target.value)}><option>Все</option><option>2GIS</option><option>Яндекс Карты</option><option>Google Maps</option><option>Telegram</option></select></label>
            <label className="select-control"><span className="sr-only">Ниша</span><select value={niche} onChange={(event) => setNiche(event.target.value)}><option>Все</option><option>Стоматология</option><option>Салон красоты</option><option>Автосервис</option><option>Юридические услуги</option><option>Кофейня</option></select></label>
            <label className="select-control clients-sort"><span className="sr-only">Сортировка</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option>Сначала релевантные</option><option>Сначала новые</option></select></label>
            <button className="solid-action" type="button" onClick={() => setShowModal(true)}><Plus size={19} />Добавить клиента</button>
          </div>

          <div className="client-list">
            {filtered.length ? filtered.map((client) => <ClientRow client={client} key={client.id} onStatusChange={updateStatus} onDetails={setSelectedClient} />) : <EmptyState>По вашему запросу клиенты не найдены.</EmptyState>}
          </div>
        </section>

        <aside className="data-side-column">
          <SidePanel className="parser-panel clients-parser">
            <div className="parser-title"><span className="parser-icon"><PawPrint size={21} /></span><div><h2>Парсер клиентов</h2><p>Собирает бизнесы из 2GIS, Яндекс Карт, Telegram и других источников и автоматически добавляет их в CRM.</p></div></div>
            <div className="source-chip-row"><SourceChip icon={MapPin} text="2GIS" tone="green" /><SourceChip icon={MapPin} text="Яндекс Карты" tone="red" /><SourceChip icon={MessageCircle} text="Telegram" tone="cyan" /><SourceChip icon={Globe2} text="Google Maps" tone="green" /></div>
            <div className="parser-stats"><span>Найдено сегодня<strong>41</strong></span><span>Новых<strong>12 <i /></strong></span></div>
            <div className="parser-filters"><p><Search />Ниши <strong>Салоны, стоматологии, автосервисы</strong></p><p><MapPin />Город <strong>Москва / СПб</strong></p><p><Sparkles />Ключевые слова <strong>сайт, CRM, автоматизация, бот</strong></p></div>
            <button className="solid-action wide-action" type="button" onClick={runParser} disabled={isParsing}>{isParsing ? <><Sparkles className="spin" size={17} />Парсим клиентов...</> : <><Send size={17} />Запустить парсер</>}</button>
            <button className="secondary-wide-action" type="button"><Settings2 size={16} />Настроить</button>
          </SidePanel>

          <SidePanel className="recommendations-panel clients-recommendations"><h2>Рекомендованные клиенты</h2>{clients.slice().sort((a, b) => b.match - a.match).slice(0, 3).map((client, index) => <button type="button" className="client-recommendation" key={client.id} onClick={() => setSelectedClient(client)}><span className={`recommendation-rank ${index === 0 ? 'purple' : index === 1 ? 'blue' : 'orange'}`}>{index + 1}</span><p><strong>{client.name}</strong><span>{client.match}% match</span></p><StatusBadge tone="green">{index === 0 ? 'Высокий приоритет' : 'Стоит написать'}</StatusBadge></button>)}<button className="text-link panel-more-link" type="button">Показать все рекомендации <ExternalLink size={15} /></button></SidePanel>

          <SidePanel className="client-stages-panel"><h2>Этапы клиентов</h2><div className="client-stage-grid">{counts.map(({ stage, value }) => <div key={stage}><span>{stage}</span><strong>{value}</strong><i className={toneByStatus[stage]} /></div>)}</div></SidePanel>

          <SidePanel className="nearest-panel clients-nearest"><h2>Ближайшие действия</h2><ClientAction icon={Send} title="Написать владельцу — Стоматология Улыбка" meta="Сегодня, 11:00" badge="Сегодня" tone="blue" /><ClientAction icon={PhoneCall} title="Созвон с владельцем — DrivePro" meta="Завтра, 14:00" badge="Завтра" tone="green" /><ClientAction icon={MessageCircle} title="Отправить КП — Партнёр" meta="21 мая, 12:00" badge="21 мая" tone="purple" /><ClientAction icon={CalendarClock} title="Напомнить о себе — Салон LIME" meta="22 мая, 10:00" badge="22 мая" tone="orange" /><button className="text-link panel-more-link" type="button">Все действия <ExternalLink size={15} /></button></SidePanel>
        </aside>
      </div>

      {showModal && <ClientModal onClose={() => setShowModal(false)} onCreate={(client) => { setClients((items) => [...items, client]); setShowModal(false) }} nextId={Math.max(...clients.map((client) => client.id)) + 1} />}
      {selectedClient && <ClientDetails client={selectedClient} onClose={() => setSelectedClient(null)} />}
    </div>
  )
}

function ClientRow({ client, onStatusChange, onDetails }: { client: Client; onStatusChange: (id: number, status: ClientStatus) => void; onDetails: (client: Client) => void }) {
  const Icon = client.icon
  return <article className="client-row"><div className="client-identity"><span className={`client-logo ${client.tone}`}><Icon size={24} /></span><div><h2>{client.name}</h2><p className="client-category">{client.category}</p><p className="client-source"><MapPin size={12} />{client.location}<span>·</span>{client.source}<span>·</span>{client.added}</p><div className="tag-row">{client.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div></div></div><div className="client-pain"><p>{client.pain}</p></div><div className="client-status-column"><StatusBadge tone={toneByStatus[client.status]}>{client.status}</StatusBadge><span>Следующий шаг</span><strong>{client.next}</strong><select aria-label={`Статус клиента ${client.name}`} value={client.status} onChange={(event) => onStatusChange(client.id, event.target.value as ClientStatus)}>{statusOptions.map((item) => <option key={item}>{item}</option>)}</select></div><div className="client-fit"><StatusBadge tone="green">{client.match >= 85 ? 'Очень релевантно' : 'Подходит'}</StatusBadge><small>{client.match}% match</small><div className="client-actions"><button type="button" onClick={() => onDetails(client)}>Подробнее</button><button type="button">Открыть <ExternalLink size={13} /></button><button className="primary-row-action" type="button" onClick={() => onStatusChange(client.id, client.status === 'Новый' ? 'Написал' : client.status)}>Изменить статус</button></div></div></article>
}

function SourceChip({ icon: Icon, text, tone }: { icon: LucideIcon; text: string; tone: UiAccent }) { return <span className={`source-chip ${tone}`}><i><Icon size={13} /></i>{text}</span> }

function ClientAction({ icon: Icon, title, meta, badge, tone }: { icon: LucideIcon; title: string; meta: string; badge: string; tone: UiAccent }) { return <div className="nearest-action"><Icon className={tone} size={24} /><p><strong>{title}</strong><span>{meta}</span></p><StatusBadge tone={tone}>{badge}</StatusBadge></div> }

function ClientModal({ onClose, onCreate, nextId }: { onClose: () => void; onCreate: (client: Client) => void; nextId: number }) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [city, setCity] = useState('Москва')
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal client-modal" onSubmit={(event) => { event.preventDefault(); if (!name.trim()) return; onCreate({ id: nextId, name: name.trim(), category: category.trim() || 'Бизнес', location: city, source: 'Добавлен вручную', added: 'Сегодня', pain: 'Нужно уточнить задачи и точки роста бизнеса.', tags: ['Новый лид'], status: 'Новый', next: 'Найти контакт', match: 70, tone: 'blue', icon: Building2 }) }} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className="metric-icon blue"><Building2 /></span><h2>Новый клиент</h2><label htmlFor="client-name">Название бизнеса</label><input id="client-name" autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Например, Studio Forma" /><label htmlFor="client-category">Ниша</label><input id="client-category" value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Например, стоматология" /><label htmlFor="client-city">Город</label><select id="client-city" value={city} onChange={(event) => setCity(event.target.value)}><option>Москва</option><option>Санкт-Петербург</option><option>Казань</option><option>Другой город</option></select><button className="solid-action wide-action" type="submit" disabled={!name.trim()}><Plus size={18} />Сохранить клиента</button></form></div>
}

function ClientDetails({ client, onClose }: { client: Client; onClose: () => void }) { const Icon = client.icon; return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="compact-modal client-details-modal" role="dialog" aria-modal="true" aria-labelledby="client-details-title" onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className={`metric-icon ${client.tone}`}><Icon /></span><h2 id="client-details-title">{client.name}</h2><p className="modal-subtitle">{client.category} · {client.location} · {client.source}</p><div className="details-grid"><span>Статус<strong>{client.status}</strong></span><span>Релевантность<strong>{client.match}% match</strong></span><span>Следующий шаг<strong>{client.next}</strong></span><span>Добавлен<strong>{client.added}</strong></span></div><p className="details-pain">{client.pain}</p><div className="tag-row">{client.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div><button className="solid-action wide-action" type="button" onClick={onClose}>Готово</button></section></div> }
