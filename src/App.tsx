import { useMemo, useState } from 'react'
import {
  BriefcaseBusiness,
  CalendarDays,
  Check,
  Folder,
  Home,
  Laptop,
  Lightbulb,
  Menu,
  Search,
  Settings,
  UserRound,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import ProjectsPage from './pages/ProjectsPage'

type Accent = 'blue' | 'green' | 'purple' | 'orange' | 'gray'

type Feature = {
  title: string
  navTitle?: string
  description: string
  guide: string
  icon: LucideIcon
  accent: Accent
}

const features: Feature[] = [
  {
    title: 'Мои проекты',
    description: 'Управление проектами',
    guide: 'Создавайте проекты, добавляйте задачи, устанавливайте сроки и отслеживайте прогресс.',
    icon: Folder,
    accent: 'blue',
  },
  {
    title: 'Работа (вакансии)',
    description: 'Поиск и отклик на вакансии',
    guide: 'Сохраняйте интересные вакансии, отслеживайте этапы откликов и собеседований.',
    icon: BriefcaseBusiness,
    accent: 'green',
  },
  {
    title: 'Фриланс',
    description: 'Заказы, клиенты и доходы',
    guide: 'Ведите список клиентов, проектов, доходов и расходов. Храните всю информацию в одном месте.',
    icon: Laptop,
    accent: 'purple',
  },
  {
    title: 'Расписание по дням',
    description: 'Планирование и задачи',
    guide: 'Планируйте свой день, добавляйте задачи и не забывайте о важных делах.',
    icon: CalendarDays,
    accent: 'orange',
  },
]

const menuItems = [
  { title: 'Главная', icon: Home, accent: 'blue' as Accent },
  ...features.map(({ title, icon, accent }) => ({ title, icon, accent })),
  { title: 'Настройки', icon: Settings, accent: 'gray' as Accent },
]

const stats = [
  { value: '3', label: 'Проекта' },
  { value: '2', label: 'Вакансии' },
  { value: '1', label: 'Клиент' },
  { value: '5', label: 'Задач на сегодня' },
]

function App() {
  const [active, setActive] = useState('Главная')
  const [search, setSearch] = useState('')
  const [isSidebarOpen, setSidebarOpen] = useState(false)
  const [showGuide, setShowGuide] = useState(false)

  const filteredFeatures = useMemo(() => {
    const query = search.trim().toLocaleLowerCase('ru')
    if (!query) return features
    return features.filter((item) =>
      `${item.title} ${item.description} ${item.guide}`.toLocaleLowerCase('ru').includes(query),
    )
  }, [search])

  const selectSection = (title: string) => {
    setActive(title)
    setSidebarOpen(false)
    if (title !== 'Главная') {
      document.querySelector('.workspace')?.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${isSidebarOpen ? 'is-open' : ''}`} aria-label="Главная навигация">
        <div className="brand-row">
          <a className="brand" href="#home" onClick={() => selectSection('Главная')}>Semix CRM</a>
          <button className="mobile-close" type="button" onClick={() => setSidebarOpen(false)} aria-label="Закрыть меню">
            <X size={22} />
          </button>
        </div>

        <nav className="side-nav">
          {menuItems.map(({ title, icon: Icon }) => (
            <button
              className={`nav-item ${active === title ? 'active' : ''}`}
              type="button"
              key={title}
              onClick={() => selectSection(title)}
            >
              <Icon size={27} strokeWidth={1.7} />
              <span>{title}</span>
            </button>
          ))}
        </nav>

        <div className="help-card">
          <div className="help-heading">
            <Lightbulb size={27} strokeWidth={1.6} />
            <strong>Как использовать</strong>
          </div>
          <p>Краткое руководство<br />по системе</p>
          <button type="button" onClick={() => setShowGuide(true)}>Открыть инструкцию</button>
        </div>
      </aside>

      {isSidebarOpen && <button className="sidebar-backdrop" aria-label="Закрыть меню" onClick={() => setSidebarOpen(false)} />}

      <header className="topbar">
        <button className="menu-toggle" type="button" onClick={() => setSidebarOpen(true)} aria-label="Открыть меню">
          <Menu size={24} />
        </button>
        <label className="search-box">
          <span className="sr-only">Поиск</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Поиск..." />
          <Search size={24} strokeWidth={1.8} />
        </label>
        <button className="profile-button" type="button" aria-label="Профиль">
          <UserRound size={24} strokeWidth={1.8} />
        </button>
      </header>

      <main className="workspace" id="home">
        {active === 'Главная' ? (
          <Dashboard
            features={filteredFeatures}
            hasSearch={Boolean(search.trim())}
            onOpen={selectSection}
            onClearSearch={() => setSearch('')}
          />
        ) : active === 'Мои проекты' ? (
          <ProjectsPage />
        ) : (
          <SectionPlaceholder title={active} onBack={() => selectSection('Главная')} />
        )}
      </main>

      {showGuide && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setShowGuide(false)}>
          <section className="guide-modal" role="dialog" aria-modal="true" aria-labelledby="guide-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="modal-close" type="button" aria-label="Закрыть" onClick={() => setShowGuide(false)}><X size={22} /></button>
            <Lightbulb className="modal-icon" size={34} />
            <h2 id="guide-title">Как использовать Semix CRM</h2>
            <p>Выберите нужный раздел в меню или воспользуйтесь карточками быстрого доступа. Поиск поможет быстро найти нужную информацию.</p>
            <button className="primary-button" type="button" onClick={() => setShowGuide(false)}>Понятно</button>
          </section>
        </div>
      )}
    </div>
  )
}

function Dashboard({
  features,
  hasSearch,
  onOpen,
  onClearSearch,
}: {
  features: Feature[]
  hasSearch: boolean
  onOpen: (title: string) => void
  onClearSearch: () => void
}) {
  return (
    <div className="dashboard">
      <section className="welcome-section">
        <h1>Главная</h1>
        <p>Добро пожаловать в Semix CRM!<br />Ваш личный помощник для организации дел, проектов и задач.</p>
      </section>

      <section className="quick-section">
        <h2>Быстрый доступ</h2>
        {features.length ? (
          <div className="quick-grid">
            {features.map(({ title, description, icon: Icon, accent }) => (
              <button className="quick-card" type="button" key={title} onClick={() => onOpen(title)}>
                <IconTile icon={Icon} accent={accent} />
                <span className="quick-copy">
                  <strong>{title}</strong>
                  <span>{description}</span>
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="empty-search">
            <Search size={28} />
            <span>Ничего не найдено</span>
            <button type="button" onClick={onClearSearch}>Очистить поиск</button>
          </div>
        )}
      </section>

      {!hasSearch && (
        <section className="guide-section">
          <h2>Как использовать систему</h2>
          <div className="guide-layout">
            <div className="steps-list">
              {features.map(({ title, guide, icon: Icon, accent }, index) => (
                <article className="guide-step" key={title}>
                  <IconTile icon={Icon} accent={accent} />
                  <div>
                    <h3>{index + 1}. {title}</h3>
                    <p>{guide}</p>
                  </div>
                </article>
              ))}
              <article className="guide-step">
                <IconTile icon={Settings} accent="gray" />
                <div>
                  <h3>5. Настройки</h3>
                  <p>Настройте систему под себя: категории,<br className="desktop-break" /> теги, уведомления и внешний вид.</p>
                </div>
              </article>
            </div>

            <div className="right-column">
              <aside className="tips-card">
                <div className="tips-title"><Lightbulb size={28} strokeWidth={1.7} /><h3>Советы</h3></div>
                <ul>
                  <li><Check />Используйте поиск для быстрого<br />нахождения нужной информации.</li>
                  <li><Check />Регулярно обновляйте статусы задач<br />и проектов.</li>
                  <li><Check />Планируйте день заранее во вкладке<br />&quot;Расписание по дням&quot;.</li>
                  <li><Check />Анализируйте свои результаты<br />и улучшайте эффективность!</li>
                </ul>
              </aside>

              <section className="stats-card">
                <h3>Статистика</h3>
                <div className="stats-grid">
                  {stats.map(({ value, label }) => (
                    <div className="stat" key={label}><strong>{value}</strong><span>{label}</span></div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}

function IconTile({ icon: Icon, accent }: { icon: LucideIcon; accent: Accent }) {
  return <span className={`icon-tile ${accent}`}><Icon size={31} strokeWidth={1.8} /></span>
}

function SectionPlaceholder({ title, onBack }: { title: string; onBack: () => void }) {
  const item = menuItems.find((entry) => entry.title === title) ?? menuItems[0]
  const Icon = item.icon
  return (
    <section className="section-placeholder">
      <IconTile icon={Icon} accent={item.accent} />
      <h1>{title}</h1>
      <p>Раздел готов к наполнению данными.</p>
      <button className="primary-button" type="button" onClick={onBack}>Вернуться на главную</button>
    </section>
  )
}

export default App
