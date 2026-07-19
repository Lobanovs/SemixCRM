import { useMemo, useState } from 'react'
import {
  Bot,
  BriefcaseBusiness,
  ChevronRight,
  CirclePlay,
  Clock3,
  ExternalLink,
  FileCode2,
  Folder,
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

type Order = {
  id: number
  title: string
  description: string
  tags: string[]
  icon: typeof Send
  accent: UiAccent
  budget: string
  source: string
  added: string
  relevance: string
  match: string
  relevanceTone: UiAccent
  next: string
  state: string
  stateTone: UiAccent
}

const orders: Order[] = [
  { id: 1, title: 'Telegram Mini App для доставки', description: 'Нужен Mini App для заказа еды и отслеживания статуса доставки. Интеграция с платежами.', tags: ['React', 'TypeScript', 'Telegram API', 'Node.js'], icon: Send, accent: 'cyan', budget: '220 000 – 300 000 ₽', source: 'Kwork', added: 'Сегодня, 10:15', relevance: 'Очень релевантно', match: '90% match', relevanceTone: 'green', next: 'Написать клиенту', state: 'Новый', stateTone: 'blue' },
  { id: 2, title: 'Лендинг для эксперта', description: 'Одностраничный лендинг под запуск онлайн-курса. Дизайн + вёрстка. Адаптив под мобильные.', tags: ['React', 'Tailwind CSS', 'UI/UX', 'Figma'], icon: PanelsTopLeft, accent: 'purple', budget: '60 000 – 90 000 ₽', source: 'Upwork', added: 'Вчера, 18:30', relevance: 'Подходит', match: '75% match', relevanceTone: 'green', next: 'Отправить кейсы', state: 'Написал', stateTone: 'orange' },
  { id: 3, title: 'CRM для салона красоты', description: 'CRM для записи клиентов, учёта услуг и аналитики. Интеграция с WhatsApp и онлайн-оплатой.', tags: ['Node.js', 'PostgreSQL', 'React', 'WhatsApp API'], icon: UsersRound, accent: 'pink', budget: '120 000 – 180 000 ₽', source: 'Freelancehunt', added: '2 дня назад', relevance: 'Средне', match: '55% match', relevanceTone: 'orange', next: 'Созвон завтра', state: 'Обсуждение', stateTone: 'purple' },
  { id: 4, title: 'Парсер вакансий и заказов', description: 'Парсер с фильтрацией по ключевым словам и отправкой в Google Sheets / Airtable.', tags: ['Python', 'BeautifulSoup', 'Selenium', 'API'], icon: FileCode2, accent: 'green', budget: '40 000 – 70 000 ₽', source: 'FL.ru', added: '3 дня назад', relevance: 'Средне', match: '50% match', relevanceTone: 'orange', next: 'Жду ответа', state: 'Откликнулся', stateTone: 'green' },
]

const orderStages = [
  ['Новый', '19', 'blue'], ['Написал', '12', 'orange'], ['Откликнулся', '14', 'green'], ['Ответили', '11', 'orange'], ['Созвон', '6', 'purple'], ['В работе', '5', 'cyan'], ['Отказ', '29', 'red'],
] as const

export default function FreelancePage() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Все')
  const [source, setSource] = useState('Все')
  const [category, setCategory] = useState('Все')
  const [showModal, setShowModal] = useState(false)

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    return orders.filter((order) => {
      const matchesText = !normalized || `${order.title} ${order.description} ${order.tags.join(' ')}`.toLocaleLowerCase('ru').includes(normalized)
      const matchesStatus = status === 'Все' || order.state === status
      const matchesSource = source === 'Все' || order.source === source
      const matchesCategory = category === 'Все' || order.tags.includes(category)
      return matchesText && matchesStatus && matchesSource && matchesCategory
    })
  }, [category, query, source, status])

  return (
    <div className="data-page freelance-page">
      <div className="data-page-grid">
        <section className="data-main-column">
          <header className="page-title-block"><h1>Фриланс</h1><p>Храните все фриланс заказы, отклики и приоритетные предложения в одном месте.</p></header>

          <div className="metrics-grid">
            <MetricCard icon={Folder} label="Всего заказов" value="96" hint="+14 за неделю" accent="blue" />
            <MetricCard icon={CirclePlay} label="Откликнулся" value="28" hint="29% от всех" accent="green" />
            <MetricCard icon={MessageSquare} label="Ответили" value="11" hint="11% от всех" accent="orange" />
            <MetricCard icon={BriefcaseBusiness} label="В работе" value="5" hint="5% от всех" accent="purple" />
          </div>

          <div className="toolbar-row freelance-toolbar">
            <label className="local-search"><span className="sr-only">Поиск заказов</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск заказов..." /><Search size={19} /></label>
            <label className="select-control"><span className="sr-only">Статус</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option>Все</option><option>Новый</option><option>Написал</option><option>Откликнулся</option><option>Обсуждение</option></select></label>
            <label className="select-control"><span className="sr-only">Источник</span><select value={source} onChange={(event) => setSource(event.target.value)}><option>Все</option><option>Upwork</option><option>Kwork</option><option>Freelancehunt</option><option>FL.ru</option></select></label>
            <label className="select-control"><span className="sr-only">Категория</span><select value={category} onChange={(event) => setCategory(event.target.value)}><option>Все</option><option>React</option><option>Node.js</option><option>Python</option></select></label>
            <label className="select-control sort-control"><span className="sr-only">Сортировка</span><select><option>Сначала релевантные</option><option>Сначала новые</option></select></label>
            <button className="solid-action" type="button" onClick={() => setShowModal(true)}><Plus size={19} />Добавить заказ</button>
          </div>

          <div className="opportunity-list freelance-list">
            {filtered.length ? filtered.map((order) => <OrderRow order={order} key={order.id} />) : <EmptyState>По вашему запросу заказы не найдены.</EmptyState>}
          </div>
        </section>

        <aside className="data-side-column">
          <SidePanel className="parser-panel freelance-parser">
            <div className="parser-title"><span className="parser-icon"><Bot size={21} /></span><div><h2>Парсер заказов</h2><p>Система отдельно парсит фриланс-заказы из разных источников и автоматически добавляет их в CRM.</p></div></div>
            <div className="source-chip-row"><ParserSource short="Up" text="Upwork" tone="green" /><ParserSource short="K" text="Kwork" tone="gray" /><ParserSource short="F" text="Freelancehunt" tone="orange" /><ParserSource short="FL" text="FL.ru" tone="blue" /><ParserSource short="T" text="Telegram" tone="cyan" /><ParserSource short="f" text="Fiverr" tone="green" /></div>
            <div className="parser-stats"><span>Найдено сегодня<strong>19</strong></span><span>Новых<strong>7 <i /></strong></span></div>
            <div className="parser-filters"><p><Search />Ключевые слова <strong>React, Next.js, CRM</strong></p><p><BriefcaseBusiness />Бюджет от <strong>30 000 ₽</strong></p><p><PanelsTopLeft />Категория <strong>Web / Bots / Automation</strong></p></div>
            <button className="solid-action wide-action" type="button"><CirclePlay size={18} />Запустить парсер</button>
            <button className="secondary-wide-action" type="button"><Settings2 size={16} />Настроить</button>
          </SidePanel>

          <SidePanel className="recommendations-panel">
            <h2>Рекомендуемые отклики</h2>
            {orders.slice(0, 3).map((order) => { const Icon = order.icon; return <button type="button" className="recommendation-item" key={order.id}><span className={`mini-order-icon ${order.accent}`}><Icon /></span><p><strong>{order.title}</strong><span>{order.budget}</span></p><span><b>{order.match}</b><StatusBadge tone={order.relevanceTone}>{order.id === 1 ? 'Высокий приоритет' : order.id === 2 ? 'Стоит откликнуться' : 'Можно откликнуться'}</StatusBadge></span></button> })}
            <button className="text-link panel-more-link" type="button">Показать все рекомендации <ChevronRight size={16} /></button>
          </SidePanel>

          <SidePanel className="order-stages-panel"><h2>Этапы заказов</h2><div className="order-stage-grid">{orderStages.map(([label, value, tone]) => <div key={label}><span>{label}</span><strong>{value}</strong><i className={tone} /></div>)}</div></SidePanel>

          <SidePanel className="nearest-panel freelance-nearest"><h2>Ближайшие действия</h2><FreelanceAction icon={Send} title="Отправить кейсы — Telegram Mini App" meta="Клиент ждёт примеры работ" badge="Сегодня" tone="green" /><FreelanceAction icon={PanelsTopLeft} title="Созвон — Лендинг для эксперта" meta="Договорились о созвоне" badge="Завтра" tone="blue" /><FreelanceAction icon={UsersRound} title="Напомнить клиенту — CRM для салона" meta="Не отвечает 2 дня" badge="Через 2 дня" tone="orange" /><button className="text-link panel-more-link" type="button">Все действия <ChevronRight size={16} /></button></SidePanel>
        </aside>
      </div>

      {showModal && <OrderModal onClose={() => setShowModal(false)} />}
    </div>
  )
}

function OrderRow({ order }: { order: Order }) {
  const Icon = order.icon
  return <article className="opportunity-row freelance-order-row"><div className="opportunity-identity"><span className={`project-logo ${order.accent}`}><Icon size={24} /></span><div><h2>{order.title}</h2><p>{order.description}</p><div className="tag-row">{order.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div></div></div><div className="opportunity-meta"><p><BriefcaseBusiness />Бюджет <strong>{order.budget}</strong></p><p><Sparkles />Источник <strong>{order.source}</strong></p><p><Clock3 />Добавлено <strong>{order.added}</strong></p></div><div className="opportunity-status freelance-order-status"><StatusBadge tone={order.relevanceTone}>{order.relevance}</StatusBadge><small>{order.match}</small><span>Следующий шаг</span><strong>{order.next}</strong><em className={order.stateTone}>● {order.state}</em><div className="stacked-order-actions"><button type="button">Подробнее</button><button type="button">Открыть <ExternalLink size={14} /></button><button className="primary-row-action" type="button">Изменить статус <ChevronRight size={15} /></button></div></div></article>
}

function ParserSource({ short, text, tone }: { short: string; text: string; tone: UiAccent }) {
  return <span className={`source-chip ${tone}`}><i>{short}</i>{text}</span>
}

function FreelanceAction({ icon: Icon, title, meta, badge, tone }: { icon: typeof Send; title: string; meta: string; badge: string; tone: UiAccent }) {
  return <div className="nearest-action"><Icon className={tone} size={24} /><p><strong>{title}</strong><span>{meta}</span></p><StatusBadge tone={tone}>{badge}</StatusBadge></div>
}

function OrderModal({ onClose }: { onClose: () => void }) {
  const [title, setTitle] = useState('')
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal" onSubmit={(event) => { event.preventDefault(); onClose() }} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className="metric-icon purple"><BriefcaseBusiness /></span><h2>Новый заказ</h2><label htmlFor="order-title">Название заказа</label><input id="order-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, Telegram-бот" /><button className="solid-action wide-action" type="submit" disabled={!title.trim()}><Plus size={18} />Сохранить заказ</button></form></div>
}
