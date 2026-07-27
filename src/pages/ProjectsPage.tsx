import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Bot,
  CircleStop,
  Code2,
  Copy,
  ExternalLink,
  Folder,
  Globe2,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Rocket,
  Search,
  Smartphone,
  Terminal,
  Trash2,
  Wand2,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { EmptyState, MetricCard, ProgressBar, SidePanel, StatusBadge, Tag } from '../components/DashboardUi'
import type { UiAccent } from '../components/DashboardUi'
import PageGuide from '../components/PageGuide'
import { PROJECTS_GUIDE } from '../guides'
import { apiRequest } from '../api'

export type Project = {
  id: number
  name: string
  description: string
  path: string
  command: string
  url: string
  port: number | null
  tags: string[]
  category: string
  status: string
  version: string
  repo_url: string
  progress: number
  last_started_at: string
  run_count: number
  archived: boolean
  created_at: string
  updated_at: string
}

export type ProjectRuntime = {
  project_id: number
  status: 'stopped' | 'running' | 'exited' | 'failed'
  pid: number | null
  started_at: string
  url: string
  port: number | null
  exit_code: number | null
  last_line: string
  reason?: string
}

type ProjectsResponse = {
  projects: Project[]
  stats: { total: number; active: number; in_progress: number; done: number; paused: number; started_today: number }
  runtime: Record<string, ProjectRuntime>
  categories: string[]
  statuses: string[]
}

type DetectedProject = {
  name: string
  description: string
  command: string
  port: number | null
  version: string
  category: string
  tags: string[]
  scripts: string[]
  exists: boolean
  kind: string
}

type StartAllResult = {
  started: { id: number; name: string; port: number | null }[]
  skipped: { id: number; name: string; reason: string }[]
  failed: { id: number; name: string; error: string }[]
}

type ProjectDraft = {
  name: string
  description: string
  path: string
  command: string
  port: string
  category: string
  status: string
  version: string
  progress: number
  tags: string[]
}

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  'Веб-приложение': Code2,
  'Веб-сайт': Globe2,
  'Бот': Bot,
  'Скрипт': Terminal,
  'Мобильное': Smartphone,
  'Другое': Folder,
}

const ACCENTS: UiAccent[] = ['blue', 'green', 'orange', 'purple', 'cyan']
const STATUS_TONES: Record<string, UiAccent> = { 'В работе': 'blue', 'Готов': 'green', 'Пауза': 'orange' }
const RUNTIME_LABELS: Record<ProjectRuntime['status'], string> = {
  running: 'Запущен',
  stopped: 'Остановлен',
  exited: 'Завершился',
  failed: 'Упал',
}
const RUNTIME_TONES: Record<ProjectRuntime['status'], UiAccent> = {
  running: 'green',
  stopped: 'gray',
  exited: 'gray',
  failed: 'red',
}

const emptyDraft = (): ProjectDraft => ({
  name: '', description: '', path: '', command: '', port: '',
  category: 'Веб-приложение', status: 'В работе', version: '', progress: 0, tags: [],
})

const draftFromProject = (project: Project): ProjectDraft => ({
  name: project.name,
  description: project.description,
  path: project.path,
  command: project.command,
  port: project.port ? String(project.port) : '',
  category: project.category,
  status: project.status,
  version: project.version,
  progress: project.progress,
  tags: project.tags,
})

const accentFor = (project: Project): UiAccent => ACCENTS[project.id % ACCENTS.length]
const iconFor = (project: Project): LucideIcon => CATEGORY_ICONS[project.category] ?? Folder

const formatMoment = (value: string) => {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [runtime, setRuntime] = useState<Record<string, ProjectRuntime>>({})
  const [stats, setStats] = useState<ProjectsResponse['stats'] | null>(null)
  const [categories, setCategories] = useState<string[]>([])
  const [statuses, setStatuses] = useState<string[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Все')
  const [category, setCategory] = useState('Все')
  const [sort, setSort] = useState('Недавние')
  const [editing, setEditing] = useState<Project | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkResult, setBulkResult] = useState<StartAllResult | null>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const selectedRef = useRef<number | null>(null)

  useEffect(() => { selectedRef.current = selectedId }, [selectedId])

  const load = useCallback(async () => {
    try {
      const data = await apiRequest<ProjectsResponse>('/api/projects', { fallback: 'Не удалось загрузить проекты' })
      setProjects(data.projects)
      setRuntime(data.runtime)
      setStats(data.stats)
      setCategories(data.categories)
      setStatuses(data.statuses)
      setSelectedId((current) => (current && data.projects.some((item) => item.id === current) ? current : data.projects[0]?.id ?? null))
      setError('')
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Не удалось загрузить проекты')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const hasRunning = useMemo(() => Object.values(runtime).some((item) => item.status === 'running'), [runtime])

  // Пока хоть один проект запущен, подтягиваем статус и свежие строки лога.
  useEffect(() => {
    if (!hasRunning) return undefined
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const data = await apiRequest<ProjectsResponse>('/api/projects', { fallback: '' })
          setRuntime(data.runtime)
          setStats(data.stats)
        } catch { /* временная ошибка сети не должна ломать экран */ }
      })()
    }, 2500)
    return () => window.clearInterval(timer)
  }, [hasRunning])

  const loadLogs = useCallback(async (projectId: number) => {
    try {
      const data = await apiRequest<{ logs: string[]; runtime: ProjectRuntime }>(
        `/api/projects/${projectId}/logs`, { fallback: '' },
      )
      if (selectedRef.current !== projectId) return
      setLogs(data.logs)
      setRuntime((current) => ({ ...current, [String(projectId)]: data.runtime }))
    } catch { /* лог не критичен для работы страницы */ }
  }, [])

  // Зависим от статуса, а не от всего runtime: иначе каждый опрос пересоздавал бы таймер.
  const selectedStatus = selectedId === null ? undefined : runtime[String(selectedId)]?.status

  useEffect(() => {
    if (selectedId === null) { setLogs([]); return undefined }
    void loadLogs(selectedId)
    if (selectedStatus !== 'running') return undefined
    const timer = window.setInterval(() => { void loadLogs(selectedId) }, 2500)
    return () => window.clearInterval(timer)
  }, [selectedId, selectedStatus, loadLogs])

  const runAction = async (projectId: number, action: () => Promise<unknown>) => {
    setBusyId(projectId)
    setError('')
    try {
      await action()
      await load()
      await loadLogs(projectId)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Действие не выполнено')
    } finally {
      setBusyId(null)
    }
  }

  const startProject = (project: Project) => runAction(project.id, () =>
    apiRequest(`/api/projects/${project.id}/start`, { method: 'POST', fallback: 'Не удалось запустить проект' }))

  const stopProject = (project: Project) => runAction(project.id, () =>
    apiRequest(`/api/projects/${project.id}/stop`, { method: 'POST', fallback: 'Не удалось остановить проект' }))

  const deleteProject = (project: Project) => {
    if (!window.confirm(`Удалить проект «${project.name}»? Папка на диске останется на месте.`)) return
    void runAction(project.id, () =>
      apiRequest(`/api/projects/${project.id}`, { method: 'DELETE', fallback: 'Не удалось удалить проект' }))
  }

  const startAll = async () => {
    const runnable = projects.filter((project) => project.command).length
    if (!window.confirm(`Запустить все проекты с командой запуска (${runnable})? Каждый поднимет свой процесс.`)) return
    setBulkBusy(true)
    setError('')
    try {
      setBulkResult(await apiRequest<StartAllResult>('/api/projects/start-all', {
        method: 'POST', fallback: 'Не удалось запустить проекты',
      }))
      await load()
    } catch (bulkError) {
      setError(bulkError instanceof Error ? bulkError.message : 'Не удалось запустить проекты')
    } finally {
      setBulkBusy(false)
    }
  }

  const stopAll = async () => {
    setBulkBusy(true)
    setError('')
    try {
      await apiRequest('/api/projects/stop-all', { method: 'POST', fallback: 'Не удалось остановить проекты' })
      setBulkResult(null)
      await load()
    } catch (bulkError) {
      setError(bulkError instanceof Error ? bulkError.message : 'Не удалось остановить проекты')
    } finally {
      setBulkBusy(false)
    }
  }

  const saveProject = async (draft: ProjectDraft) => {
    const payload = {
      name: draft.name.trim(),
      description: draft.description.trim(),
      path: draft.path.trim(),
      command: draft.command.trim(),
      port: draft.port ? Number(draft.port) : null,
      tags: draft.tags,
      category: draft.category,
      status: draft.status,
      version: draft.version.trim(),
      progress: draft.progress,
    }
    if (editing) {
      await apiRequest(`/api/projects/${editing.id}`, { method: 'PUT', body: payload, fallback: 'Не удалось сохранить проект' })
    } else {
      await apiRequest('/api/projects', { method: 'POST', body: payload, fallback: 'Не удалось добавить проект' })
    }
    setShowModal(false)
    setEditing(null)
    await load()
  }

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    const result = projects.filter((project) => {
      const haystack = `${project.name} ${project.description} ${project.tags.join(' ')} ${project.path}`.toLocaleLowerCase('ru')
      const matchesQuery = !normalized || haystack.includes(normalized)
      const matchesStatus = status === 'Все' || project.status === status
      const matchesCategory = category === 'Все' || project.category === category
      return matchesQuery && matchesStatus && matchesCategory
    })
    if (sort === 'Готовность') return [...result].sort((a, b) => b.progress - a.progress)
    if (sort === 'Название') return [...result].sort((a, b) => a.name.localeCompare(b.name, 'ru'))
    return result
  }, [projects, query, sort, status, category])

  const selected = projects.find((project) => project.id === selectedId) ?? null
  const selectedRuntime = selected ? runtime[String(selected.id)] : undefined
  const runningCount = Object.values(runtime).filter((item) => item.status === 'running').length

  const copyUrl = async (value: string) => {
    if (!value) return
    await navigator.clipboard?.writeText(value)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  return (
    <div className="data-page projects-page">
      <div className="data-page-grid">
        <section className="data-main-column">
          <header className="page-title-block">
            <h1>Мои проекты</h1>
            <p>Добавьте папку проекта — и запускайте его одной кнопкой прямо отсюда.</p>
          </header>

          <PageGuide
            sectionId="projects"
            title="Как пользоваться разделом «Мои проекты»"
            intro="Раздел хранит папки ваших проектов и запускает их дев-серверы, не выходя из CRM."
            steps={PROJECTS_GUIDE}
          />

          {error && <div className="page-empty-state" role="alert">{error}</div>}

          <div className="metrics-grid">
            <MetricCard icon={Folder} label="Всего проектов" value={stats?.total ?? 0} hint={`${stats?.done ?? 0} готовы`} accent="blue" />
            <MetricCard icon={Rocket} label="Активные" value={stats?.active ?? 0} hint={`${stats?.paused ?? 0} на паузе`} accent="green" />
            <MetricCard icon={Code2} label="В разработке" value={stats?.in_progress ?? 0} hint="статус «В работе»" accent="orange" />
            <MetricCard icon={Play} label="Сейчас запущено" value={runningCount} hint={`${stats?.started_today ?? 0} стартов сегодня`} accent="purple" />
          </div>

          <div className="toolbar-row">
            <label className="local-search">
              <span className="sr-only">Поиск проектов</span>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск проектов..." />
              <Search size={19} />
            </label>
            <label className="select-control">
              <span className="sr-only">Статус</span>
              <select value={status} onChange={(event) => setStatus(event.target.value)}>
                <option>Все</option>
                {statuses.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label className="select-control">
              <span className="sr-only">Категория</span>
              <select value={category} onChange={(event) => setCategory(event.target.value)}>
                <option>Все</option>
                {categories.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label className="select-control sort-control">
              <span className="sr-only">Сортировка</span>
              <select value={sort} onChange={(event) => setSort(event.target.value)}>
                <option>Недавние</option>
                <option>Готовность</option>
                <option>Название</option>
              </select>
            </label>
            <button className="solid-action" type="button" data-guide="projects-add" onClick={() => { setEditing(null); setShowModal(true) }}>
              <Plus size={19} />Добавить проект
            </button>
            {runningCount ? (
              <button className="secondary-wide-action" type="button" data-guide="projects-bulk" onClick={() => void stopAll()} disabled={bulkBusy}>
                <CircleStop size={17} />Остановить все ({runningCount})
              </button>
            ) : (
              <button className="secondary-wide-action" type="button" data-guide="projects-bulk" onClick={() => void startAll()} disabled={bulkBusy || !projects.some((project) => project.command)}>
                <Rocket size={17} />{bulkBusy ? 'Запускаю…' : 'Запустить все'}
              </button>
            )}
          </div>

          {bulkResult && (
            <div className="bulk-run-summary">
              <p><strong>Запущено: {bulkResult.started.length}</strong>{bulkResult.started.length ? ` — ${bulkResult.started.map((item) => item.name).join(', ')}` : ''}</p>
              {bulkResult.skipped.length > 0 && (
                <p>Пропущено: {bulkResult.skipped.map((item) => `${item.name} (${item.reason})`).join(', ')}</p>
              )}
              {bulkResult.failed.length > 0 && (
                <p className="field-error">Не запустилось: {bulkResult.failed.map((item) => `${item.name} — ${item.error}`).join('; ')}</p>
              )}
              <button className="text-link" type="button" onClick={() => setBulkResult(null)}>Скрыть</button>
            </div>
          )}

          <div className="project-list">
            {loading ? <EmptyState>Загружаю проекты…</EmptyState>
              : filtered.length ? filtered.map((project) => (
                <ProjectRow
                  key={project.id}
                  project={project}
                  runtime={runtime[String(project.id)]}
                  selected={selectedId === project.id}
                  busy={busyId === project.id}
                  onSelect={() => setSelectedId(project.id)}
                  onStart={() => void startProject(project)}
                  onStop={() => void stopProject(project)}
                  onEdit={() => { setEditing(project); setShowModal(true) }}
                  onDelete={() => deleteProject(project)}
                />
              ))
                : <EmptyState>{projects.length ? 'По вашему запросу проекты не найдены.' : 'Пока нет ни одного проекта. Нажмите «Добавить проект» и укажите папку на диске.'}</EmptyState>}
          </div>
        </section>

        <aside className="data-side-column">
          {selected ? (
            <SidePanel className="project-summary-panel">
              <div className="panel-title-row">
                <h2>{selected.name}</h2>
                <StatusBadge tone={STATUS_TONES[selected.status] ?? 'gray'}>{selected.status}</StatusBadge>
              </div>
              <p>{selected.description || 'Описание не заполнено.'}</p>

              <h3>Запуск</h3>
              <div className="project-meta-grid">
                <span><Terminal />Команда</span><strong>{selected.command || 'не задана'}</strong>
                <span><Folder />Папка</span><strong title={selected.path}>{selected.path || 'не задана'}</strong>
                <span><Play />Состояние</span>
                <strong>{RUNTIME_LABELS[selectedRuntime?.status ?? 'stopped']}{selectedRuntime?.pid ? ` · PID ${selectedRuntime.pid}` : ''}</strong>
                <span>Последний старт</span><strong>{formatMoment(selected.last_started_at)}</strong>
              </div>

              {selectedRuntime?.url && (
                <>
                  <h3>Адрес</h3>
                  <div className="copy-field">
                    <Globe2 />
                    <a href={selectedRuntime.url} target="_blank" rel="noreferrer">{selectedRuntime.url}</a>
                    <button type="button" onClick={() => void copyUrl(selectedRuntime.url)} aria-label="Копировать адрес"><Copy size={18} /></button>
                  </div>
                  {copied && <span className="copy-feedback">Адрес скопирован</span>}
                </>
              )}

              <h3>Лог запуска</h3>
              <pre className="project-log-view" data-guide="projects-log" aria-label="Лог запуска проекта">
                {logs.length ? logs.slice(-120).join('\n') : 'Пока пусто. Запустите проект, чтобы увидеть вывод.'}
              </pre>
              <button className="text-link" type="button" onClick={() => void loadLogs(selected.id)}>
                <RefreshCw size={15} /> Обновить лог
              </button>

              {selectedRuntime?.status === 'running' ? (
                <button className="solid-action wide-action" type="button" onClick={() => void stopProject(selected)} disabled={busyId === selected.id}>
                  <CircleStop size={19} />Остановить проект
                </button>
              ) : (
                <button className="solid-action wide-action" type="button" onClick={() => void startProject(selected)} disabled={busyId === selected.id || !selected.command}>
                  <Play size={19} />Запустить проект
                </button>
              )}
            </SidePanel>
          ) : (
            <SidePanel className="project-summary-panel"><h2>Проект не выбран</h2><p>Добавьте проект, чтобы управлять им отсюда.</p></SidePanel>
          )}

          <SidePanel>
            <h2>Быстрый запуск</h2>
            {projects.length ? (
              <div className="quick-launch-grid">
                {projects.filter((item) => item.command).slice(0, 4).map((project) => {
                  const Icon = iconFor(project)
                  const state = runtime[String(project.id)]
                  return (
                    <button
                      type="button"
                      key={project.id}
                      onClick={() => (state?.status === 'running' ? void stopProject(project) : void startProject(project))}
                      disabled={busyId === project.id}
                    >
                      <Icon />
                      <strong>{project.name}</strong>
                      <span>{state?.status === 'running' ? 'Остановить' : 'Запустить'}</span>
                    </button>
                  )
                })}
              </div>
            ) : <EmptyState>Добавьте проект с командой запуска.</EmptyState>}
          </SidePanel>
        </aside>
      </div>

      {showModal && (
        <ProjectModal
          initial={editing ? draftFromProject(editing) : emptyDraft()}
          categories={categories}
          statuses={statuses}
          isEdit={Boolean(editing)}
          onClose={() => { setShowModal(false); setEditing(null) }}
          onSave={saveProject}
        />
      )}
    </div>
  )
}

function ProjectRow({
  project, runtime, selected, busy, onSelect, onStart, onStop, onEdit, onDelete,
}: {
  project: Project
  runtime?: ProjectRuntime
  selected: boolean
  busy: boolean
  onSelect: () => void
  onStart: () => void
  onStop: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const Icon = iconFor(project)
  const state = runtime?.status ?? 'stopped'
  const isRunning = state === 'running'
  return (
    <article className={`project-row ${selected ? 'selected' : ''}`} onClick={onSelect}>
      <div className="project-identity">
        <span className={`project-logo ${accentFor(project)}`}><Icon size={25} /></span>
        <div>
          <div className="project-name-line">
            <h2>{project.name}</h2>
            <StatusBadge tone={STATUS_TONES[project.status] ?? 'gray'}>{project.status}</StatusBadge>
            <StatusBadge tone={RUNTIME_TONES[state]}>{RUNTIME_LABELS[state]}</StatusBadge>
          </div>
          <p>{project.description || project.path || 'Описание не заполнено.'}</p>
          <div className="tag-row">{project.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div>
        </div>
      </div>
      <div className="project-details">
        <div className="project-meta-grid">
          <span><Terminal />Команда</span><strong>{project.command || '—'}</strong>
          <span><Globe2 />Адрес</span>
          <strong>{runtime?.url || (project.port ? `http://localhost:${project.port}` : '—')}</strong>
          <span>Версия</span><strong>{project.version || '—'}</strong>
          <span>Запусков</span><strong>{project.run_count}</strong>
        </div>
        <div className="project-progress">
          <span>Готовность</span>
          <ProgressBar value={project.progress} tone={accentFor(project)} />
          <strong>{project.progress}%</strong>
        </div>
        <div className="row-actions">
          <button type="button" onClick={(event) => { event.stopPropagation(); onEdit() }}><Pencil size={14} /> Изменить</button>
          {runtime?.url && (
            <button type="button" onClick={(event) => { event.stopPropagation(); window.open(runtime.url, '_blank', 'noopener') }}>
              Открыть <ExternalLink size={15} />
            </button>
          )}
          <button type="button" onClick={(event) => { event.stopPropagation(); onDelete() }}><Trash2 size={14} /> Удалить</button>
          {isRunning ? (
            <button className="primary-row-action" type="button" data-guide="projects-row-start" disabled={busy} onClick={(event) => { event.stopPropagation(); onStop() }}>
              Остановить <CircleStop size={16} />
            </button>
          ) : (
            <button
              className="primary-row-action"
              type="button"
              data-guide="projects-row-start"
              disabled={busy || !project.command}
              title={project.command ? '' : 'Задайте команду запуска в настройках проекта'}
              onClick={(event) => { event.stopPropagation(); onStart() }}
            >
              Запустить <Play size={16} />
            </button>
          )}
        </div>
        {state === 'failed' && (runtime?.reason || runtime?.last_line) && (
          <p className="project-run-error">
            Не запустился (код {runtime.exit_code}): {runtime.reason || runtime.last_line}
          </p>
        )}
      </div>
    </article>
  )
}

function ProjectModal({
  initial, categories, statuses, isEdit, onClose, onSave,
}: {
  initial: ProjectDraft
  categories: string[]
  statuses: string[]
  isEdit: boolean
  onClose: () => void
  onSave: (draft: ProjectDraft) => Promise<void>
}) {
  const [draft, setDraft] = useState<ProjectDraft>(initial)
  const [detecting, setDetecting] = useState(false)
  const [detectNote, setDetectNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const update = (patch: Partial<ProjectDraft>) => setDraft((current) => ({ ...current, ...patch }))

  const detect = async () => {
    if (!draft.path.trim()) return
    setDetecting(true)
    setDetectNote('')
    try {
      const found = await apiRequest<DetectedProject>('/api/projects/detect', {
        method: 'POST', body: { path: draft.path.trim() }, fallback: 'Не удалось прочитать папку',
      })
      if (!found.exists) {
        setDetectNote('Папка не найдена — проверьте путь.')
        return
      }
      update({
        name: draft.name || found.name,
        description: draft.description || found.description,
        command: draft.command || found.command,
        port: draft.port || (found.port ? String(found.port) : ''),
        version: draft.version || found.version,
        category: found.category || draft.category,
        tags: draft.tags.length ? draft.tags : found.tags,
      })
      setDetectNote(found.command
        ? `Определено: ${found.kind}. Команда — ${found.command}`
        : `Определено: ${found.kind}. Команду запуска задайте вручную.`)
    } catch (detectError) {
      setDetectNote(detectError instanceof Error ? detectError.message : 'Не удалось прочитать папку')
    } finally {
      setDetecting(false)
    }
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!draft.name.trim()) return
    setSaving(true)
    setError('')
    try {
      await onSave(draft)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Не удалось сохранить проект')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form className="compact-modal project-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button>
        <span className="metric-icon blue"><Folder /></span>
        <h2>{isEdit ? 'Настройки проекта' : 'Новый проект'}</h2>

        <label htmlFor="project-path">Папка проекта</label>
        <div className="inline-field">
          <input
            id="project-path"
            value={draft.path}
            onChange={(event) => update({ path: event.target.value })}
            placeholder="C:\Users\Admin\Desktop\my-site"
          />
          <button type="button" onClick={() => void detect()} disabled={detecting || !draft.path.trim()}>
            <Wand2 size={16} />{detecting ? 'Читаю…' : 'Определить'}
          </button>
        </div>
        {detectNote && <p className="field-hint">{detectNote}</p>}

        <label htmlFor="project-title">Название</label>
        <input id="project-title" autoFocus value={draft.name} onChange={(event) => update({ name: event.target.value })} placeholder="Например, Интернет-магазин" />

        <label htmlFor="project-command">Команда запуска</label>
        <input id="project-command" value={draft.command} onChange={(event) => update({ command: event.target.value })} placeholder="npm run dev" />

        <label htmlFor="project-port">Порт (если известен)</label>
        <input id="project-port" inputMode="numeric" value={draft.port} onChange={(event) => update({ port: event.target.value.replace(/\D+/g, '') })} placeholder="5173" />

        <label htmlFor="project-description">Описание</label>
        <input id="project-description" value={draft.description} onChange={(event) => update({ description: event.target.value })} placeholder="Коротко о проекте" />

        <label htmlFor="project-category">Категория</label>
        <select id="project-category" value={draft.category} onChange={(event) => update({ category: event.target.value })}>
          {(categories.length ? categories : [draft.category]).map((item) => <option key={item}>{item}</option>)}
        </select>

        <label htmlFor="project-status">Статус</label>
        <select id="project-status" value={draft.status} onChange={(event) => update({ status: event.target.value })}>
          {(statuses.length ? statuses : [draft.status]).map((item) => <option key={item}>{item}</option>)}
        </select>

        <label htmlFor="project-progress">Готовность: {draft.progress}%</label>
        <input
          id="project-progress"
          type="range"
          min={0}
          max={100}
          step={5}
          value={draft.progress}
          onChange={(event) => update({ progress: Number(event.target.value) })}
        />

        {error && <p className="field-error" role="alert">{error}</p>}

        <button className="solid-action wide-action" type="submit" disabled={!draft.name.trim() || saving}>
          <Plus size={18} />{saving ? 'Сохраняю…' : isEdit ? 'Сохранить' : 'Добавить проект'}
        </button>
      </form>
    </div>
  )
}
