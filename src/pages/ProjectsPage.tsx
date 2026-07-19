import { useMemo, useState } from 'react'
import {
  Check,
  CheckSquare,
  CirclePlay,
  Clock3,
  Code2,
  Copy,
  ExternalLink,
  Folder,
  Globe2,
  Image,
  Plus,
  Rocket,
  Search,
  UsersRound,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { EmptyState, MetricCard, ProgressBar, SidePanel, StatusBadge, Tag } from '../components/DashboardUi'
import type { UiAccent } from '../components/DashboardUi'

type Project = {
  id: number
  title: string
  description: string
  tags: string[]
  icon: LucideIcon
  accent: UiAccent
  status: 'В работе' | 'Готов' | 'Пауза'
  statusTone: UiAccent
  updated: string
  url: string
  version: string
  category: string
  progress: number
}

const initialProjects: Project[] = [
  {
    id: 1,
    title: 'Личный сайт',
    description: 'Персональный сайт-портфолио с блогом и контактной формой.',
    tags: ['Next.js', 'TypeScript', 'Tailwind CSS'],
    icon: Globe2,
    accent: 'blue',
    status: 'В работе',
    statusTone: 'blue',
    updated: 'Сегодня, 10:32',
    url: 'http://localhost:3000',
    version: '1.2.0',
    category: 'Веб-приложение',
    progress: 65,
  },
  {
    id: 2,
    title: 'Task Manager',
    description: 'Приложение для управления задачами и проектами команды.',
    tags: ['React', 'Node.js', 'MongoDB'],
    icon: CheckSquare,
    accent: 'green',
    status: 'Готов',
    statusTone: 'green',
    updated: 'Вчера, 18:45',
    url: 'http://localhost:5173',
    version: '1.0.3',
    category: 'Веб-приложение',
    progress: 100,
  },
  {
    id: 3,
    title: 'CRM для клиентов',
    description: 'Система управления клиентами и сделками для малого бизнеса.',
    tags: ['React', 'Node.js', 'PostgreSQL'],
    icon: UsersRound,
    accent: 'orange',
    status: 'Пауза',
    statusTone: 'orange',
    updated: '3 дня назад',
    url: 'http://localhost:4000',
    version: '0.9.2',
    category: 'Веб-приложение',
    progress: 40,
  },
  {
    id: 4,
    title: 'Портфолио',
    description: 'Фотографии работ и кейсы с описанием проектов.',
    tags: ['Next.js', 'Sanity', 'Tailwind CSS'],
    icon: Image,
    accent: 'purple',
    status: 'Готов',
    statusTone: 'green',
    updated: '5 дней назад',
    url: 'http://localhost:3010',
    version: '1.1.0',
    category: 'Веб-сайт',
    progress: 90,
  },
]

const activity = [
  ['Сегодня, 10:32', 'Обновлены стили главной страницы'],
  ['Вчера, 21:17', 'Добавлена форма обратной связи'],
  ['Вчера, 18:05', 'Исправлены отступы на мобильной версии'],
]

export default function ProjectsPage() {
  const [projects, setProjects] = useState(initialProjects)
  const [selectedId, setSelectedId] = useState(1)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Все')
  const [sort, setSort] = useState('Недавние')
  const [showModal, setShowModal] = useState(false)
  const [copied, setCopied] = useState(false)

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    const result = projects.filter((project) => {
      const matchesQuery = !normalized || `${project.title} ${project.description} ${project.tags.join(' ')}`.toLocaleLowerCase('ru').includes(normalized)
      const matchesStatus = status === 'Все' || project.status === status
      return matchesQuery && matchesStatus
    })
    if (sort === 'Готовность') return [...result].sort((a, b) => b.progress - a.progress)
    if (sort === 'Название') return [...result].sort((a, b) => a.title.localeCompare(b.title, 'ru'))
    return result
  }, [projects, query, sort, status])

  const selected = projects.find((project) => project.id === selectedId) ?? projects[0]

  const addProject = (title: string) => {
    const nextId = Math.max(...projects.map((item) => item.id)) + 1
    const project: Project = {
      id: nextId,
      title,
      description: 'Новый проект — добавьте описание, технологии и адрес запуска.',
      tags: ['React'],
      icon: Code2,
      accent: 'cyan',
      status: 'В работе',
      statusTone: 'blue',
      updated: 'Только что',
      url: 'http://localhost:3000',
      version: '0.1.0',
      category: 'Веб-приложение',
      progress: 10,
    }
    setProjects((current) => [project, ...current])
    setSelectedId(nextId)
    setShowModal(false)
  }

  const copyUrl = async () => {
    await navigator.clipboard?.writeText(selected.url)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  return (
    <div className="data-page projects-page">
      <div className="data-page-grid">
        <section className="data-main-column">
          <header className="page-title-block">
            <h1>Мои проекты</h1>
            <p>Ваши личные проекты, приложения и идеи в одном месте.</p>
          </header>

          <div className="metrics-grid">
            <MetricCard icon={Folder} label="Всего проектов" value={projects.length} hint="+1 за неделю" accent="blue" />
            <MetricCard icon={Rocket} label="Активные" value={projects.filter((item) => item.status !== 'Пауза').length} hint="75% от всех" accent="green" />
            <MetricCard icon={Code2} label="В разработке" value="2" hint="50% от всех" accent="orange" />
            <MetricCard icon={CirclePlay} label="Запущено сегодня" value="2" hint="+1 к вчера" accent="purple" />
          </div>

          <div className="toolbar-row">
            <label className="local-search">
              <span className="sr-only">Поиск проектов</span>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск проектов..." />
              <Search size={19} />
            </label>
            <label className="select-control"><span className="sr-only">Статус</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option>Все</option><option>В работе</option><option>Готов</option><option>Пауза</option></select></label>
            <label className="select-control"><span className="sr-only">Категория</span><select><option>Категория: Все</option><option>Веб-приложение</option><option>Веб-сайт</option></select></label>
            <label className="select-control sort-control"><span className="sr-only">Сортировка</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option>Недавние</option><option>Готовность</option><option>Название</option></select></label>
            <button className="solid-action" type="button" onClick={() => setShowModal(true)}><Plus size={19} />Добавить проект</button>
          </div>

          <div className="project-list">
            {filtered.length ? filtered.map((project) => {
              const Icon = project.icon
              return (
                <article className={`project-row ${selected.id === project.id ? 'selected' : ''}`} key={project.id} onClick={() => setSelectedId(project.id)}>
                  <div className="project-identity">
                    <span className={`project-logo ${project.accent}`}><Icon size={25} /></span>
                    <div>
                      <div className="project-name-line"><h2>{project.title}</h2><StatusBadge tone={project.statusTone}>{project.status}</StatusBadge></div>
                      <p>{project.description}</p>
                      <div className="tag-row">{project.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div>
                    </div>
                  </div>
                  <div className="project-details">
                    <div className="project-meta-grid">
                      <span><Clock3 />Обновлён</span><strong>{project.updated}</strong>
                      <span><Globe2 />Локально</span><a href={project.url} onClick={(event) => event.preventDefault()}>{project.url}</a>
                      <span>Версия</span><strong>{project.version}</strong>
                      <span>Категория</span><strong>{project.category}</strong>
                    </div>
                    <div className="project-progress"><span>Готовность</span><ProgressBar value={project.progress} tone={project.accent} /><strong>{project.progress}%</strong></div>
                    <div className="row-actions">
                      <button type="button" onClick={() => setSelectedId(project.id)}>Подробнее</button>
                      <button type="button">Открыть <ExternalLink size={15} /></button>
                      <button className="primary-row-action" type="button">Запустить <CirclePlay size={16} /></button>
                    </div>
                  </div>
                </article>
              )
            }) : <EmptyState>По вашему запросу проекты не найдены.</EmptyState>}
          </div>
        </section>

        <aside className="data-side-column">
          <SidePanel className="project-summary-panel">
            <div className="panel-title-row"><h2>{selected.title}</h2><StatusBadge tone={selected.statusTone}>{selected.status}</StatusBadge></div>
            <p>{selected.description}</p>
            <h3>Основные возможности</h3>
            <ul className="check-list">
              <li><Check />Адаптивный дизайн и тёмная тема</li>
              <li><Check />Блог на Markdown с категориями</li>
              <li><Check />Форма обратной связи</li>
              <li><Check />SEO оптимизация и метатеги</li>
            </ul>
            <h3>Адрес для запуска</h3>
            <div className="copy-field"><Globe2 /><a href={selected.url} onClick={(event) => event.preventDefault()}>{selected.url}</a><button type="button" onClick={copyUrl} aria-label="Копировать адрес"><Copy size={18} /></button></div>
            {copied && <span className="copy-feedback">Адрес скопирован</span>}
            <h3>Последняя активность</h3>
            <div className="activity-list">{activity.map(([date, text]) => <div key={date}><span /><p><strong>{date}</strong>{text}</p></div>)}</div>
            <button className="text-link" type="button">Показать всю активность</button>
            <button className="solid-action wide-action" type="button"><CirclePlay size={19} />Запустить проект</button>
          </SidePanel>

          <SidePanel>
            <h2>Быстрый запуск</h2>
            <div className="quick-launch-grid">
              {projects.filter((item) => item.status !== 'Пауза').slice(0, 3).map((project) => {
                const Icon = project.icon
                return <button type="button" key={project.id} onClick={() => setSelectedId(project.id)}><Icon /><strong>{project.title}</strong><span>{project.url.split(':').pop()}</span></button>
              })}
            </div>
          </SidePanel>
        </aside>
      </div>

      {showModal && <ProjectModal onClose={() => setShowModal(false)} onCreate={addProject} />}
    </div>
  )
}

function ProjectModal({ onClose, onCreate }: { onClose: () => void; onCreate: (title: string) => void }) {
  const [title, setTitle] = useState('')
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form className="compact-modal" onSubmit={(event) => { event.preventDefault(); if (title.trim()) onCreate(title.trim()) }} onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button>
        <span className="metric-icon blue"><Folder /></span>
        <h2>Новый проект</h2>
        <label htmlFor="project-title">Название проекта</label>
        <input id="project-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, Интернет-магазин" />
        <button className="solid-action wide-action" type="submit" disabled={!title.trim()}><Plus size={18} />Добавить проект</button>
      </form>
    </div>
  )
}
