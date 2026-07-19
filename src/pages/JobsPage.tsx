import { useMemo, useState } from 'react'
import {
  Bell,
  BriefcaseBusiness,
  CalendarDays,
  Check,
  ChevronRight,
  CirclePlay,
  Clock3,
  ExternalLink,
  Filter,
  MessageSquare,
  Plus,
  Search,
  Settings2,
  UsersRound,
  X,
} from 'lucide-react'
import { EmptyState, MetricCard, SidePanel, StatusBadge, Tag } from '../components/DashboardUi'
import type { UiAccent } from '../components/DashboardUi'

type Job = {
  id: number
  company: string
  role: string
  description: string
  tags: string[]
  logo: string
  logoTone: 'yandex' | 'vk' | 'sber' | 'tbank'
  source: string
  salary: string
  location: string
  added: string
  status: string
  statusTone: UiAccent
  next: string
  nextTone: UiAccent
}

const jobs: Job[] = [
  { id: 1, company: 'Яндекс', role: 'Frontend-разработчик (React)', description: 'Разработка пользовательских интерфейсов в сервисах Яндекса для миллионов пользователей.', tags: ['React', 'TypeScript', 'Redux', 'JavaScript'], logo: 'Я', logoTone: 'yandex', source: 'HH', salary: '200 000 – 280 000 ₽', location: 'Москва, гибрид', added: 'Сегодня, 10:32', status: 'Сохранено', statusTone: 'blue', next: 'Жду решения', nextTone: 'blue' },
  { id: 2, company: 'VK (ВКонтакте)', role: 'Fullstack-разработчик (Node.js)', description: 'Разработка новых функций и поддержка существующих сервисов платформы ВКонтакте.', tags: ['Node.js', 'TypeScript', 'PostgreSQL', 'REST'], logo: 'VK', logoTone: 'vk', source: 'LinkedIn', salary: '180 000 – 240 000 ₽', location: 'Санкт-Петербург, офис', added: 'Вчера, 15:45', status: 'Откликнулся', statusTone: 'green', next: 'Жду ответа', nextTone: 'green' },
  { id: 3, company: 'Сбер', role: 'Backend-разработчик (Go)', description: 'Проектирование и разработка высоконагруженных сервисов и микросервисной архитектуры.', tags: ['Go', 'gRPC', 'PostgreSQL', 'Kafka'], logo: '✓', logoTone: 'sber', source: 'HH', salary: '220 000 – 300 000 ₽', location: 'Москва, офис', added: '2 дня назад', status: 'Ответили', statusTone: 'orange', next: 'Интервью завтра в 15:00', nextTone: 'orange' },
  { id: 4, company: 'Т-Банк', role: 'DevOps-инженер', description: 'Поддержка и развитие инфраструктуры, автоматизация деплоя и CI/CD процессов.', tags: ['Docker', 'Kubernetes', 'AWS', 'GitLab CI'], logo: '◈', logoTone: 'tbank', source: 'Habr Career', salary: '160 000 – 220 000 ₽', location: 'Удалённо', added: '5 дней назад', status: 'Отказ', statusTone: 'red', next: '—', nextTone: 'gray' },
]

const stageStats = [
  ['Сохранено', '52', 'blue'],
  ['Откликнулся', '34', 'green'],
  ['Ответили', '12', 'orange'],
  ['Собеседование', '6', 'purple'],
  ['Оффер', '2', 'cyan'],
  ['Отказ', '22', 'red'],
] as const

export default function JobsPage() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Все')
  const [source, setSource] = useState('Все')
  const [showModal, setShowModal] = useState(false)

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    return jobs.filter((job) => {
      const matchesText = !normalized || `${job.company} ${job.role} ${job.description} ${job.tags.join(' ')}`.toLocaleLowerCase('ru').includes(normalized)
      const matchesStatus = status === 'Все' || job.status === status
      const matchesSource = source === 'Все' || job.source === source
      return matchesText && matchesStatus && matchesSource
    })
  }, [query, source, status])

  return (
    <div className="data-page jobs-page">
      <div className="data-page-grid">
        <section className="data-main-column">
          <header className="page-title-block">
            <h1>Работа (вакансии)</h1>
            <p>Храните все вакансии, отклики и этапы найма в одном месте.</p>
          </header>

          <div className="metrics-grid">
            <MetricCard icon={BriefcaseBusiness} label="Всего вакансий" value="128" hint="+12 за неделю" accent="blue" />
            <MetricCard icon={CirclePlay} label="Откликнулся" value="34" hint="26% от всех" accent="green" />
            <MetricCard icon={MessageSquare} label="Ответили" value="12" hint="9% от всех" accent="orange" />
            <MetricCard icon={UsersRound} label="Собеседования" value="6" hint="5% от всех" accent="purple" />
          </div>

          <div className="toolbar-row jobs-toolbar">
            <label className="local-search"><span className="sr-only">Поиск вакансий</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск вакансий..." /><Search size={19} /></label>
            <label className="select-control"><span className="sr-only">Статус</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option>Все</option><option>Сохранено</option><option>Откликнулся</option><option>Ответили</option><option>Отказ</option></select></label>
            <label className="select-control"><span className="sr-only">Источник</span><select value={source} onChange={(event) => setSource(event.target.value)}><option>Все</option><option>HH</option><option>LinkedIn</option><option>Habr Career</option></select></label>
            <label className="select-control sort-control"><span className="sr-only">Сортировка</span><select><option>Сначала новые</option><option>Сначала релевантные</option></select></label>
            <button className="solid-action" type="button" onClick={() => setShowModal(true)}><Plus size={19} />Добавить вакансию</button>
          </div>

          <div className="opportunity-list">
            {filtered.length ? filtered.map((job) => <JobRow job={job} key={job.id} />) : <EmptyState>По вашему запросу вакансии не найдены.</EmptyState>}
          </div>
        </section>

        <aside className="data-side-column">
          <SidePanel className="parser-panel">
            <div className="parser-title"><span className="parser-icon">♙</span><div><h2>Парсер вакансий</h2><p>Собирает вакансии из разных источников и добавляет их в CRM.</p></div></div>
            <div className="source-chip-row"><SourceChip text="HH" tone="red" /><SourceChip text="LinkedIn" tone="blue" icon={<BriefcaseBusiness />} /><SourceChip text="Telegram" tone="cyan" /><SourceChip text="Habr Career" tone="gray" /><SourceChip text="Remote" tone="blue" /></div>
            <div className="parser-stats"><span>Найдено сегодня<strong>27</strong></span><span>Новых<strong>8 <i /></strong></span></div>
            <h3>Фильтры парсера</h3>
            <div className="parser-filters"><p><Filter />Ключевые слова <strong>React, TypeScript, Go</strong></p><p><BriefcaseBusiness />Зарплата от <strong>от 120 000 ₽</strong></p><p><CalendarDays />Формат работы <strong>Любой</strong></p><p><UsersRound />Город / Страна <strong>Любой</strong></p></div>
            <button className="solid-action wide-action" type="button"><CirclePlay size={18} />Запустить парсер</button>
            <button className="secondary-wide-action" type="button"><Settings2 size={16} />Настроить</button>
          </SidePanel>

          <SidePanel className="stages-panel">
            <h2>Этапы откликов</h2>
            <div className="stage-stat-grid">{stageStats.map(([label, value, tone]) => <div key={label}><span>{label}</span><strong>{value}</strong><i className={tone} /></div>)}</div>
            <p className="conversion-note">Конверсия в собеседование: <strong>14%</strong></p>
          </SidePanel>

          <SidePanel className="nearest-panel">
            <h2>Ближайшие действия</h2>
            <NearestAction icon={CalendarDays} title="Интервью: Сбер — Backend Go" meta="Завтра, 15:00" tone="purple" badge="Завтра" />
            <NearestAction icon={Bell} title="Напомнить: Ответ от VK" meta="Написать рекрутеру" tone="orange" badge="Через 2 дня" />
            <NearestAction icon={Check} title="Тестовое задание: Яндекс" meta="Дедлайн: 28 мая" tone="green" badge="20 мая" />
            <button className="text-link" type="button">Все действия <ChevronRight size={16} /></button>
          </SidePanel>
        </aside>
      </div>

      {showModal && <JobModal onClose={() => setShowModal(false)} />}
    </div>
  )
}

function JobRow({ job }: { job: Job }) {
  return (
    <article className="opportunity-row">
      <div className="opportunity-identity">
        <span className={`company-logo ${job.logoTone}`}>{job.logo}</span>
        <div><h2>{job.company}</h2><h3>{job.role}</h3><p>{job.description}</p><div className="tag-row">{job.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div></div>
      </div>
      <div className="opportunity-meta">
        <p><BriefcaseBusiness />Источник <strong>{job.source}</strong></p>
        <p><span className="meta-symbol">₽</span>Зарплата <strong>{job.salary}</strong></p>
        <p><span className="meta-symbol">⌖</span>Локация <strong>{job.location}</strong></p>
        <p><Clock3 />Добавлено <strong>{job.added}</strong></p>
        <div className="opportunity-buttons"><button type="button">Подробнее</button><button type="button">Открыть <ExternalLink size={14} /></button></div>
      </div>
      <div className="opportunity-status"><StatusBadge tone={job.statusTone}>{job.status}</StatusBadge><span>Следующий шаг</span><strong>{job.next}</strong><button className="primary-row-action" type="button">Изменить статус <ChevronRight size={15} /></button></div>
    </article>
  )
}

function SourceChip({ text, tone, icon }: { text: string; tone: UiAccent; icon?: React.ReactNode }) {
  return <span className={`source-chip ${tone}`}><i>{icon ?? text.slice(0, 1)}</i>{text}</span>
}

function NearestAction({ icon: Icon, title, meta, tone, badge }: { icon: typeof CalendarDays; title: string; meta: string; tone: UiAccent; badge: string }) {
  return <div className="nearest-action"><Icon className={tone} size={24} /><p><strong>{title}</strong><span>{meta}</span></p><StatusBadge tone={tone}>{badge}</StatusBadge></div>
}

function JobModal({ onClose }: { onClose: () => void }) {
  const [title, setTitle] = useState('')
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal" onSubmit={(event) => { event.preventDefault(); onClose() }} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className="metric-icon blue"><BriefcaseBusiness /></span><h2>Новая вакансия</h2><label htmlFor="job-title">Название вакансии</label><input id="job-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, Frontend-разработчик" /><button className="solid-action wide-action" type="submit" disabled={!title.trim()}><Plus size={18} />Сохранить вакансию</button></form></div>
}
