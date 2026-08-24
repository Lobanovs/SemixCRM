import { useEffect, useMemo, useState, type MouseEvent } from 'react'
import {
  BriefcaseBusiness,
  Bookmark,
  CalendarDays,
  Check,
  Folder,
  Home,
  Laptop,
  Lightbulb,
  Menu,
  Moon,
  PawPrint,
  Search,
  Settings,
  Sun,
  UserRound,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import ProjectsPage from './pages/ProjectsPage'
import JobsPage from './pages/JobsPage'
import FreelancePage from './pages/FreelancePage'
import SchedulePage from './pages/SchedulePage'
import ClientsPage from './pages/ClientsPage'
import SettingsPage from './pages/SettingsPage'
import UsefulThingsPage from './pages/UsefulThingsPage'
import PageGuide from './components/PageGuide'
import ActionCenter from './components/ActionCenter'
import { HOME_GUIDE } from './guides'

type Accent = 'blue' | 'green' | 'purple' | 'orange' | 'gray'

// Переход между разделами идёт по устойчивому id: раньше сравнивались подписи меню,
// и переименование пункта молча ломало маршрут.
export type SectionId = 'home' | 'projects' | 'jobs' | 'freelance' | 'schedule' | 'useful' | 'clients' | 'settings'

type Feature = {
  id: SectionId
  title: string
  description: string
  guide: string
  icon: LucideIcon
  accent: Accent
}

const features: Feature[] = [
  {
    id: 'projects',
    title: 'Мои проекты',
    description: 'Управление проектами',
    guide: 'Добавьте папку проекта, задайте команду запуска — и стартуйте его одной кнопкой прямо из CRM.',
    icon: Folder,
    accent: 'blue',
  },
  {
    id: 'jobs',
    title: 'Работа (вакансии)',
    description: 'Поиск и отклик на вакансии',
    guide: 'Собирайте вакансии с hh.ru, Хабр Карьеры и Telegram-каналов и ведите этапы откликов.',
    icon: BriefcaseBusiness,
    accent: 'green',
  },
  {
    id: 'freelance',
    title: 'Фриланс',
    description: 'Заказы, клиенты и доходы',
    guide: 'Ведите список клиентов, проектов, доходов и расходов. Храните всю информацию в одном месте.',
    icon: Laptop,
    accent: 'purple',
  },
  {
    id: 'schedule',
    title: 'Расписание по дням',
    description: 'Планирование и задачи',
    guide: 'Планируйте свой день, добавляйте задачи и не забывайте о важных делах.',
    icon: CalendarDays,
    accent: 'orange',
  },
  {
    id: 'useful',
    title: 'Полезные вещи',
    description: 'Промпты, сайты и статьи',
    guide: 'Храните промпты, полезные сайты, магазины и статьи по отдельным вкладкам.',
    icon: Bookmark,
    accent: 'blue',
  },
]

const menuItems: { id: SectionId; title: string; icon: LucideIcon; accent: Accent }[] = [
  { id: 'home', title: 'Главная', icon: Home, accent: 'blue' },
  ...features.map(({ id, title, icon, accent }) => ({ id, title, icon, accent })),
  { id: 'clients', title: 'Волк с Уолл-стрит', icon: PawPrint, accent: 'blue' },
  { id: 'settings', title: 'Настройки', icon: Settings, accent: 'gray' },
]

const validSections = new Set<SectionId>(menuItems.map((item) => item.id))

function sectionFromHash(): SectionId {
  const value = window.location.hash.replace(/^#/, '') as SectionId
  return validSections.has(value) ? value : 'home'
}

function App() {
  const [active, setActive] = useState<SectionId>(sectionFromHash)
  const [search, setSearch] = useState('')
  const [isSidebarOpen, setSidebarOpen] = useState(false)
  const [showGuide, setShowGuide] = useState(false)
  const [isDark, setIsDark] = useState(() => window.localStorage.getItem('semix-crm-theme') === 'dark')

  useEffect(() => {
    if (!window.location.hash) window.history.replaceState(null, '', '#home')
    const followHash = () => setActive(sectionFromHash())
    window.addEventListener('hashchange', followHash)
    window.addEventListener('popstate', followHash)
    return () => {
      window.removeEventListener('hashchange', followHash)
      window.removeEventListener('popstate', followHash)
    }
  }, [])

  // Прокручиваем после commit React: до него браузерное scroll anchoring
  // восстанавливало позицию старого раздела поверх только что открытого.
  useEffect(() => {
    document.querySelector('.workspace')?.scrollTo({ top: 0, behavior: 'auto' })
  }, [active])

  const filteredFeatures = useMemo(() => {
    const query = search.trim().toLocaleLowerCase('ru')
    if (!query) return features
    return features.filter((item) =>
      `${item.title} ${item.description} ${item.guide}`.toLocaleLowerCase('ru').includes(query),
    )
  }, [search])

  const selectSection = (id: SectionId) => {
    setActive(id)
    setSidebarOpen(false)
    if (window.location.hash !== `#${id}`) window.history.pushState(null, '', `#${id}`)
  }

  const openProfile = () => {
    selectSection('settings')
    window.setTimeout(() => document.getElementById('profile')?.focus(), 0)
  }

  const openBrand = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    selectSection('home')
  }

  return (
    <div
      className={`app-shell ${isDark ? 'theme-dark' : ''}`}
      data-theme={isDark ? 'premium-dark' : undefined}
    >
      <a className="skip-link" href="#main-content">Перейти к содержимому</a>
      <aside className={`sidebar ${isSidebarOpen ? 'is-open' : ''}`} aria-label="Главная навигация">
        <div className="brand-row">
          <a className="brand" href="#home" onClick={openBrand}>Semix CRM</a>
          <button className="mobile-close" type="button" onClick={() => setSidebarOpen(false)} aria-label="Закрыть меню">
            <X size={22} />
          </button>
        </div>

        <nav className="side-nav" data-guide="home-nav">
          {menuItems.map(({ id, title, icon: Icon }) => (
            <button
              className={`nav-item ${active === id ? 'active' : ''}`}
              type="button"
              key={id}
              onClick={() => selectSection(id)}
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
        {active === 'home' ? <label className="search-box" data-guide="home-search">
          <span className="sr-only">Поиск по разделам</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Найти раздел..." />
          <Search size={24} strokeWidth={1.8} />
        </label> : <div className="topbar-section-title">{menuItems.find((item) => item.id === active)?.title}</div>}
        <button
          className="theme-toggle"
          type="button"
          data-guide="home-theme"
          aria-label={isDark ? 'Включить светлую тему' : 'Включить тёмную тему'}
          aria-pressed={isDark}
          title={isDark ? 'Светлая тема' : 'Тёмная тема'}
          onClick={() => setIsDark((current) => {
            const next = !current
            window.localStorage.setItem('semix-crm-theme', next ? 'dark' : 'light')
            return next
          })}
        >
          {isDark ? <Sun size={21} strokeWidth={1.8} /> : <Moon size={21} strokeWidth={1.8} />}
        </button>
        <button className="profile-button" type="button" aria-label="Открыть рабочий профиль" onClick={openProfile}>
          <UserRound size={24} strokeWidth={1.8} />
        </button>
      </header>

      <main className="workspace" id="main-content" tabIndex={-1}>
        {active === 'home' ? (
          <Dashboard
            features={filteredFeatures}
            hasSearch={Boolean(search.trim())}
            onOpen={selectSection}
            onClearSearch={() => setSearch('')}
          />
        ) : active === 'projects' ? (
          <ProjectsPage />
        ) : active === 'jobs' ? (
          <JobsPage />
        ) : active === 'freelance' ? (
          <FreelancePage />
        ) : active === 'schedule' ? (
          <SchedulePage />
        ) : active === 'useful' ? (
          <UsefulThingsPage />
        ) : active === 'clients' ? (
          <ClientsPage />
        ) : active === 'settings' ? (
          <SettingsPage />
        ) : (
          <SectionPlaceholder id={active} onBack={() => selectSection('home')} />
        )}
      </main>

      {showGuide && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setShowGuide(false)}>
          <section className="guide-modal" role="dialog" aria-modal="true" aria-labelledby="guide-title" onMouseDown={(event) => event.stopPropagation()}>
            <button className="modal-close" type="button" aria-label="Закрыть" onClick={() => setShowGuide(false)}><X size={22} /></button>
            <Lightbulb className="modal-icon" size={34} />
            <h2 id="guide-title">Где искать инструкцию</h2>
            <p>В каждом разделе под заголовком есть блок «Как пользоваться» с пошаговой инструкцией. Кнопка «Показать на экране» внутри него подсветит нужные элементы прямо в интерфейсе.</p>
            <p>При первом заходе в раздел инструкция открывается сама, дальше — по кнопке.</p>
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
  onOpen: (id: SectionId) => void
  onClearSearch: () => void
}) {
  return (
    <div className="dashboard">
      <section className="welcome-section">
        <h1>Сегодня</h1>
        <p>Главное за день без переходов между десятками списков.</p>
      </section>

      {!hasSearch && <ActionCenter onOpen={onOpen} />}

      <PageGuide
        sectionId="home"
        title="Как пользоваться Semix CRM"
        intro="Короткая вводная по оболочке. В каждом разделе есть своя инструкция с таким же туром по кнопкам."
        steps={HOME_GUIDE}
      />

      <section className="quick-section">
        <h2>Быстрый доступ</h2>
        {features.length ? (
          <div className="quick-grid">
            {features.map(({ id, title, description, icon: Icon, accent }) => (
              <button className="quick-card" type="button" key={id} onClick={() => onOpen(id)}>
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
          <h2>Что в каждом разделе</h2>
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
                  <h3>{features.length + 1}. Настройки</h3>
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

function SectionPlaceholder({ id, onBack }: { id: SectionId; onBack: () => void }) {
  const item = menuItems.find((entry) => entry.id === id) ?? menuItems[0]
  const Icon = item.icon
  return (
    <section className="section-placeholder">
      <IconTile icon={Icon} accent={item.accent} />
      <h1>{item.title}</h1>
      <p>Раздел готов к наполнению данными.</p>
      <button className="primary-button" type="button" onClick={onBack}>Вернуться на главную</button>
    </section>
  )
}

export default App
