import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Archive,
  BriefcaseBusiness,
  CalendarDays,
  CirclePlay,
  Clock3,
  ExternalLink,
  Filter,
  MessageSquare,
  Plus,
  Search,
  Settings2,
  Trash2,
  UsersRound,
  X,
} from 'lucide-react'
import { EmptyState, MetricCard, SidePanel, StatusBadge, Tag } from '../components/DashboardUi'
import type { UiAccent } from '../components/DashboardUi'
import PageGuide from '../components/PageGuide'
import { JOBS_GUIDE } from '../guides'
import { apiRequest } from '../api'
import { JOB_SOURCE_META } from './jobSources'
import ProgressiveListFooter from '../components/ProgressiveListFooter'

export type Job = {
  id: number
  source: string
  external_id: string
  company: string
  role: string
  description: string
  url: string
  tags: string[]
  salary_min: number | null
  salary_max: number | null
  salary_text: string
  location: string
  employment: string
  published_at: string
  discovered_at: string
  relevance: number
  relevance_reasons: string[]
  match_score: number
  status: string
  next_step: string
  note: string
  archived: boolean
}

type JobStats = {
  total: number
  found_today: number
  archived: number
  applied: number
  replied: number
  interviews: number
  offers: number
  stages: Record<string, number>
  conversion: number
}

type SourceStatus = { source: string; status: string; checked_at: string; found_count: number; error: string }

type JobsResponse = {
  jobs: Job[]
  stats: JobStats
  sources: SourceStatus[]
  statuses: string[]
  available: string[]
}

export type JobSettings = {
  sources: string[]
  keywords: string[]
  excluded_keywords: string[]
  telegram_channels: string[]
  area: string
  salary_min: number
  remote_only: boolean
  per_source_limit: number
}

type ParseRun = {
  run_id: string
  status: string
  message: string
  error: string
  inserted: number
  duplicates: number
  sources: Record<string, { status: string; error?: string; found?: number; new?: number }>
}

const STATUS_TONES: Record<string, UiAccent> = {
  'Сохранено': 'blue',
  'Откликнулся': 'green',
  'Ответили': 'orange',
  'Собеседование': 'purple',
  'Оффер': 'cyan',
  'Отказ': 'red',
}

const SOURCE_STATE_LABELS: Record<string, string> = {
  idle: 'Не проверялся',
  done: 'Собрано',
  empty: 'Нет новых',
  error: 'Ошибка',
}

const LOGO_ACCENTS: UiAccent[] = ['blue', 'green', 'orange', 'purple', 'cyan', 'pink']

const initials = (company: string) => {
  const words = company.replace(/[@«»"']/g, '').trim().split(/\s+/).filter(Boolean)
  if (!words.length) return '—'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return `${words[0][0]}${words[1][0]}`.toUpperCase()
}

const logoAccent = (job: Job): UiAccent => LOGO_ACCENTS[job.id % LOGO_ACCENTS.length]

const formatMoment = (value: string) => {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [stats, setStats] = useState<JobStats | null>(null)
  const [sources, setSources] = useState<SourceStatus[]>([])
  const [statuses, setStatuses] = useState<string[]>([])
  const [settings, setSettings] = useState<JobSettings | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Все')
  const [source, setSource] = useState('Все')
  const [sort, setSort] = useState('relevance')
  const [archived, setArchived] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [run, setRun] = useState<ParseRun | null>(null)
  const [runId, setRunId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [archivingAll, setArchivingAll] = useState(false)
  const [visibleCount, setVisibleCount] = useState(50)

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ sort, archived: String(archived) })
      if (query.trim()) params.set('query', query.trim())
      if (status !== 'Все') params.set('status', status)
      if (source !== 'Все') params.set('source', source)
      const data = await apiRequest<JobsResponse>(`/api/jobs?${params}`, { fallback: 'Не удалось загрузить вакансии' })
      setJobs(data.jobs)
      setStats(data.stats)
      setSources(data.sources)
      setStatuses(data.statuses)
      setError('')
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Не удалось загрузить вакансии')
    } finally {
      setLoading(false)
    }
  }, [query, status, source, sort, archived])

  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 200)
    return () => window.clearTimeout(timer)
  }, [load])

  useEffect(() => setVisibleCount(50), [jobs])
  const visibleJobs = jobs.slice(0, visibleCount)

  useEffect(() => {
    void (async () => {
      try {
        setSettings(await apiRequest<JobSettings>('/api/jobs/settings', { fallback: '' }))
      } catch { /* настройки не критичны для просмотра списка */ }
    })()
  }, [])

  // Пока идёт сбор, опрашиваем его статус и обновляем список по завершении.
  useEffect(() => {
    if (!runId) return undefined
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const snapshot = await apiRequest<ParseRun>(`/api/jobs/parse/${runId}`, { fallback: '' })
          setRun(snapshot)
          if (['done', 'partial', 'error', 'missing'].includes(snapshot.status)) {
            setRunId('')
            await load()
          }
        } catch { /* следующий тик повторит запрос */ }
      })()
    }, 1500)
    return () => window.clearInterval(timer)
  }, [runId, load])

  const startParse = async () => {
    setError('')
    try {
      const started = await apiRequest<{ run_id: string; error?: string }>('/api/jobs/parse', {
        method: 'POST', fallback: 'Не удалось запустить сбор вакансий',
      })
      if (!started.run_id) {
        setError(started.error || 'Не удалось запустить сбор вакансий')
        return
      }
      setRunId(started.run_id)
      setRun({ run_id: started.run_id, status: 'running', message: 'Собираю вакансии…', error: '', inserted: 0, duplicates: 0, sources: {} })
    } catch (parseError) {
      setError(parseError instanceof Error ? parseError.message : 'Не удалось запустить сбор вакансий')
    }
  }

  const updateJob = async (jobId: number, patch: Record<string, unknown>) => {
    setError('')
    try {
      await apiRequest(`/api/jobs/${jobId}`, { method: 'PUT', body: patch, fallback: 'Не удалось обновить вакансию' })
      await load()
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Не удалось обновить вакансию')
    }
  }

  const deleteJob = async (job: Job) => {
    if (!window.confirm(`Удалить вакансию «${job.role}»?`)) return
    try {
      await apiRequest(`/api/jobs/${job.id}`, { method: 'DELETE', fallback: 'Не удалось удалить вакансию' })
      await load()
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Не удалось удалить вакансию')
    }
  }

  const archiveAllJobs = async () => {
    const count = stats?.total ?? jobs.length
    if (!count || !window.confirm(`Перенести все активные вакансии (${count}) в архив?`)) return
    setArchivingAll(true)
    setError('')
    setNotice('')
    try {
      const result = await apiRequest<{ archived_count: number }>('/api/jobs/archive-all', {
        method: 'POST', fallback: 'Не удалось архивировать вакансии',
      })
      setNotice(`Перенесено в архив: ${result.archived_count}`)
      await load()
    } catch (archiveError) {
      setError(archiveError instanceof Error ? archiveError.message : 'Не удалось архивировать вакансии')
    } finally {
      setArchivingAll(false)
    }
  }

  const createJob = async (payload: Record<string, unknown>) => {
    await apiRequest('/api/jobs', { method: 'POST', body: payload, fallback: 'Не удалось добавить вакансию' })
    setShowModal(false)
    await load()
  }

  const saveSettings = async (next: JobSettings) => {
    const saved = await apiRequest<JobSettings>('/api/jobs/settings', {
      method: 'PUT', body: next, fallback: 'Не удалось сохранить настройки',
    })
    setSettings(saved)
    setShowSettings(false)
  }

  const stageStats = useMemo(() => {
    const stages = stats?.stages ?? {}
    return statuses.map((label) => [label, String(stages[label] ?? 0), STATUS_TONES[label] ?? 'gray'] as const)
  }, [stats, statuses])

  const isParsing = Boolean(runId)
  const keywordsMissing = settings !== null && settings.keywords.length === 0

  return (
    <div className="data-page jobs-page">
      <div className="data-page-grid">
        <section className="data-main-column">
          <header className="page-title-block">
            <h1>Работа (вакансии)</h1>
            <p>Храните все вакансии, отклики и этапы найма в одном месте.</p>
          </header>

          <PageGuide
            sectionId="jobs"
            title="Как пользоваться разделом «Работа (вакансии)»"
            intro="Трекер откликов с этапами плюс сбор вакансий с hh.ru, Хабр Карьеры и Telegram-каналов."
            steps={JOBS_GUIDE}
          />

          {error && <div className="page-empty-state" role="alert">{error}</div>}
          {notice && <div className="jobs-action-notice" role="status" aria-live="polite">{notice}</div>}

          <div className="metrics-grid">
            <MetricCard icon={BriefcaseBusiness} label="Всего вакансий" value={stats?.total ?? 0} hint={`+${stats?.found_today ?? 0} сегодня`} accent="blue" />
            <MetricCard icon={CirclePlay} label="Откликнулся" value={stats?.applied ?? 0} hint={stats?.total ? `${Math.round((stats.applied / stats.total) * 100)}% от всех` : '—'} accent="green" />
            <MetricCard icon={MessageSquare} label="Ответили" value={stats?.replied ?? 0} hint={stats?.total ? `${Math.round((stats.replied / stats.total) * 100)}% от всех` : '—'} accent="orange" />
            <MetricCard icon={UsersRound} label="Собеседования" value={stats?.interviews ?? 0} hint={`${stats?.offers ?? 0} офферов`} accent="purple" />
          </div>

          <div className="toolbar-row jobs-toolbar">
            <label className="local-search">
              <span className="sr-only">Поиск вакансий</span>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск вакансий..." />
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
              <span className="sr-only">Источник</span>
              <select value={source} onChange={(event) => setSource(event.target.value)}>
                <option>Все</option>
                {Object.entries(JOB_SOURCE_META).map(([key, meta]) => <option key={key} value={key}>{meta.label}</option>)}
                <option value="manual">Вручную</option>
              </select>
            </label>
            <label className="select-control sort-control">
              <span className="sr-only">Сортировка</span>
              <select value={sort} onChange={(event) => setSort(event.target.value)}>
                <option value="relevance">Сначала релевантные</option>
                <option value="new">Сначала новые</option>
                <option value="salary">По зарплате</option>
                <option value="company">По компании</option>
              </select>
            </label>
            <button className="secondary-wide-action" type="button" onClick={() => setArchived((current) => !current)}>
              {archived ? 'Показать активные' : `Архив (${stats?.archived ?? 0})`}
            </button>
            {!archived && (
              <button
                className="secondary-wide-action archive-all-action"
                type="button"
                onClick={() => void archiveAllJobs()}
                disabled={archivingAll || !(stats?.total ?? jobs.length)}
              >
                <Archive size={17} />{archivingAll ? 'Архивирую…' : 'Все в архив'}
              </button>
            )}
            <button className="solid-action" type="button" data-guide="jobs-add" onClick={() => setShowModal(true)}><Plus size={19} />Добавить вакансию</button>
          </div>

          <div className="opportunity-list">
            {loading ? <EmptyState>Загружаю вакансии…</EmptyState>
              : jobs.length ? visibleJobs.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  statuses={statuses}
                  onStatus={(value) => void updateJob(job.id, { status: value })}
                  onNote={(value) => void updateJob(job.id, { note: value })}
                  onArchive={() => void updateJob(job.id, { archived: !job.archived })}
                  onDelete={() => void deleteJob(job)}
                />
              ))
                : <EmptyState>{archived ? 'В архиве пусто.' : 'Вакансий пока нет. Добавьте вручную или запустите сбор в панели справа.'}</EmptyState>}
            <ProgressiveListFooter shown={visibleJobs.length} total={jobs.length} step={50} onMore={() => setVisibleCount((count) => Math.min(count + 50, jobs.length))} onAll={() => setVisibleCount(jobs.length)} />
          </div>
        </section>

        <aside className="data-side-column">
          <SidePanel className="parser-panel">
            <div className="parser-title">
              <span className="parser-icon">♙</span>
              <div><h2>Парсер вакансий</h2><p>Собирает вакансии из hh.ru, Хабр Карьеры и Telegram-каналов.</p></div>
            </div>

            <div className="source-chip-row" data-guide="jobs-sources">
              {sources.map((item) => {
                const meta = JOB_SOURCE_META[item.source]
                return (
                  <span className={`source-chip ${meta?.tone ?? 'gray'}`} key={item.source} title={item.error || SOURCE_STATE_LABELS[item.status] || item.status}>
                    <i>{meta?.short ?? item.source.slice(0, 1).toUpperCase()}</i>
                    {meta?.label ?? item.source}
                  </span>
                )
              })}
            </div>

            <div className="parser-stats">
              <span>Найдено сегодня<strong>{stats?.found_today ?? 0}</strong></span>
              <span>Всего в базе<strong>{stats?.total ?? 0}</strong></span>
            </div>

            {keywordsMissing && (
              <p className="field-hint">Задайте ключевые слова — без них у всех вакансий будет нулевая релевантность.</p>
            )}

            <h3>Фильтры парсера</h3>
            <div className="parser-filters">
              <p><Filter />Ключевые слова <strong>{settings?.keywords.join(', ') || 'не заданы'}</strong></p>
              <p><BriefcaseBusiness />Зарплата от <strong>{settings?.salary_min ? `${settings.salary_min.toLocaleString('ru-RU')} ₽` : 'любая'}</strong></p>
              <p><CalendarDays />Формат работы <strong>{settings?.remote_only ? 'Только удалённо' : 'Любой'}</strong></p>
              <p><UsersRound />Регион <strong>{settings?.area || 'Россия'}</strong></p>
              <p><MessageSquare />Каналы <strong>{settings?.telegram_channels.map((item) => `@${item}`).join(', ') || 'не заданы'}</strong></p>
            </div>

            <button className="solid-action wide-action" type="button" data-guide="jobs-run" onClick={() => void startParse()} disabled={isParsing}>
              <CirclePlay size={18} />{isParsing ? 'Собираю…' : 'Запустить парсер'}
            </button>
            <button className="secondary-wide-action" type="button" data-guide="jobs-settings" onClick={() => setShowSettings(true)} disabled={!settings}>
              <Settings2 size={16} />Настроить
            </button>

            {run && (
              <div className="parser-run-state">
                <p>{run.message}</p>
                {Object.entries(run.sources).map(([key, state]) => (
                  <p key={key}>
                    <strong>{JOB_SOURCE_META[key]?.label ?? key}</strong>{' — '}
                    {state.status === 'error' ? (state.error || 'ошибка') : `найдено ${state.found ?? 0}, новых ${state.new ?? 0}`}
                  </p>
                ))}
              </div>
            )}
          </SidePanel>

          <SidePanel className="stages-panel">
            <h2>Этапы откликов</h2>
            <div className="stage-stat-grid">
              {stageStats.map(([label, value, tone]) => (
                <div key={label}><span>{label}</span><strong>{value}</strong><i className={tone} /></div>
              ))}
            </div>
            <p className="conversion-note">Конверсия в собеседование: <strong>{stats?.conversion ?? 0}%</strong></p>
          </SidePanel>
        </aside>
      </div>

      {showModal && <JobModal onClose={() => setShowModal(false)} onCreate={createJob} />}
      {showSettings && settings && (
        <JobSettingsModal settings={settings} onClose={() => setShowSettings(false)} onSave={saveSettings} />
      )}
    </div>
  )
}

function JobRow({
  job, statuses, onStatus, onNote, onArchive, onDelete,
}: {
  job: Job
  statuses: string[]
  onStatus: (value: string) => void
  onNote: (value: string) => void
  onArchive: () => void
  onDelete: () => void
}) {
  const [note, setNote] = useState(job.note)
  const [noteOpen, setNoteOpen] = useState(false)
  const meta = JOB_SOURCE_META[job.source]

  useEffect(() => { setNote(job.note) }, [job.note])

  return (
    <article className="opportunity-row">
      <div className="opportunity-identity">
        <span className={`company-logo ${logoAccent(job)}`}>{initials(job.company)}</span>
        <div>
          <h2>{job.company || 'Без названия'}</h2>
          <h3>{job.role}</h3>
          <p>{job.description || 'Описание не указано.'}</p>
          <div className="tag-row">{job.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div>
        </div>
      </div>
      <div className="opportunity-meta">
        <p><BriefcaseBusiness />Источник <strong>{meta?.label ?? (job.source === 'manual' ? 'Вручную' : job.source)}</strong></p>
        <p><span className="meta-symbol">₽</span>Зарплата <strong>{job.salary_text || 'не указана'}</strong></p>
        <p><span className="meta-symbol">⌖</span>Локация <strong>{job.location || job.employment || '—'}</strong></p>
        <p><Clock3 />Найдена <strong>{formatMoment(job.discovered_at)}</strong></p>
        <div className="opportunity-buttons">
          <button type="button" data-guide="jobs-note" onClick={() => setNoteOpen((current) => !current)}>Заметка</button>
          {job.url && <button type="button" onClick={() => window.open(job.url, '_blank', 'noopener')}>Открыть <ExternalLink size={14} /></button>}
          <button type="button" onClick={onArchive}>{job.archived ? 'Вернуть' : 'В архив'}</button>
          <button type="button" onClick={onDelete}><Trash2 size={14} /></button>
        </div>
        {noteOpen && (
          <div className="inline-field">
            <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Например: написал рекрутеру 26 июля" />
            <button type="button" onClick={() => onNote(note)} disabled={note === job.note}>Сохранить</button>
          </div>
        )}
      </div>
      <div className="opportunity-status">
        <StatusBadge tone={STATUS_TONES[job.status] ?? 'gray'}>{job.status}</StatusBadge>
        <span>Релевантность</span>
        <strong title={job.relevance_reasons.join('; ')}>{job.match_score}%</strong>
        <span>Следующий шаг</span>
        <strong>{job.next_step || '—'}</strong>
        <label className="select-control" data-guide="jobs-status">
          <span className="sr-only">Статус вакансии</span>
          <select value={job.status} onChange={(event) => onStatus(event.target.value)}>
            {statuses.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
      </div>
    </article>
  )
}

function JobModal({ onClose, onCreate }: { onClose: () => void; onCreate: (payload: Record<string, unknown>) => Promise<void> }) {
  const [role, setRole] = useState('')
  const [company, setCompany] = useState('')
  const [url, setUrl] = useState('')
  const [salaryText, setSalaryText] = useState('')
  const [location, setLocation] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!role.trim()) return
    setSaving(true)
    setError('')
    try {
      await onCreate({
        role: role.trim(), company: company.trim(), url: url.trim(),
        salary_text: salaryText.trim(), location: location.trim(),
        description: description.trim(), source: 'manual',
      })
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Не удалось добавить вакансию')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form className="compact-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button>
        <span className="metric-icon blue"><BriefcaseBusiness /></span>
        <h2>Новая вакансия</h2>

        <label htmlFor="job-title">Название вакансии</label>
        <input id="job-title" autoFocus value={role} onChange={(event) => setRole(event.target.value)} placeholder="Например, Frontend-разработчик" />

        <label htmlFor="job-company">Компания</label>
        <input id="job-company" value={company} onChange={(event) => setCompany(event.target.value)} placeholder="Например, Яндекс" />

        <label htmlFor="job-url">Ссылка на вакансию</label>
        <input id="job-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://hh.ru/vacancy/..." />

        <label htmlFor="job-salary">Зарплата</label>
        <input id="job-salary" value={salaryText} onChange={(event) => setSalaryText(event.target.value)} placeholder="200 000 – 280 000 ₽" />

        <label htmlFor="job-location">Локация и формат</label>
        <input id="job-location" value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Москва, гибрид" />

        <label htmlFor="job-description">Описание</label>
        <input id="job-description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Коротко о задачах" />

        {error && <p className="field-error" role="alert">{error}</p>}

        <button className="solid-action wide-action" type="submit" disabled={!role.trim() || saving}>
          <Plus size={18} />{saving ? 'Сохраняю…' : 'Сохранить вакансию'}
        </button>
      </form>
    </div>
  )
}

function JobSettingsModal({
  settings, onClose, onSave,
}: {
  settings: JobSettings
  onClose: () => void
  onSave: (next: JobSettings) => Promise<void>
}) {
  const [draft, setDraft] = useState<JobSettings>(settings)
  // Списки редактируются как обычный текст: разбор на каждое нажатие съедал бы запятую.
  const [keywordsText, setKeywordsText] = useState(settings.keywords.join(', '))
  const [excludedText, setExcludedText] = useState(settings.excluded_keywords.join(', '))
  const [channelsText, setChannelsText] = useState(settings.telegram_channels.join(', '))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const update = (patch: Partial<JobSettings>) => setDraft((current) => ({ ...current, ...patch }))
  const toList = (value: string) => value.split(',').map((item) => item.trim()).filter(Boolean)

  const toggleSource = (key: string) => update({
    sources: draft.sources.includes(key) ? draft.sources.filter((item) => item !== key) : [...draft.sources, key],
  })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!draft.sources.length) { setError('Выберите хотя бы один источник'); return }
    setSaving(true)
    setError('')
    try {
      await onSave({
        ...draft,
        keywords: toList(keywordsText),
        excluded_keywords: toList(excludedText),
        telegram_channels: toList(channelsText),
      })
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Не удалось сохранить настройки')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form className="compact-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button>
        <span className="metric-icon green"><Settings2 /></span>
        <h2>Настройки парсера вакансий</h2>

        <span className="field-label">Источники</span>
        <div className="source-toggle-row">
          {Object.entries(JOB_SOURCE_META).map(([key, meta]) => (
            <label key={key} className="source-toggle">
              <input type="checkbox" checked={draft.sources.includes(key)} onChange={() => toggleSource(key)} />
              {meta.label}
            </label>
          ))}
        </div>

        <label htmlFor="job-keywords">Ключевые слова (через запятую)</label>
        <input
          id="job-keywords"
          value={keywordsText}
          onChange={(event) => setKeywordsText(event.target.value)}
          placeholder="react, typescript, next.js"
        />

        <label htmlFor="job-excluded">Стоп-слова</label>
        <input
          id="job-excluded"
          value={excludedText}
          onChange={(event) => setExcludedText(event.target.value)}
          placeholder="стажёр, неоплачиваемая"
        />

        <label htmlFor="job-channels">Telegram-каналы (без @)</label>
        <input
          id="job-channels"
          value={channelsText}
          onChange={(event) => setChannelsText(event.target.value)}
          placeholder="forfrontend, jobs_hunt"
        />

        <label htmlFor="job-area">Регион для hh.ru</label>
        <input id="job-area" value={draft.area} onChange={(event) => update({ area: event.target.value })} placeholder="Россия, Москва, Казань…" />

        <label htmlFor="job-salary-min">Зарплата от, ₽</label>
        <input
          id="job-salary-min"
          inputMode="numeric"
          value={draft.salary_min ? String(draft.salary_min) : ''}
          onChange={(event) => update({ salary_min: Number(event.target.value.replace(/\D+/g, '')) || 0 })}
          placeholder="150000"
        />

        <label htmlFor="job-limit">Максимум вакансий с источника: {draft.per_source_limit}</label>
        <input
          id="job-limit"
          type="range"
          min={10}
          max={100}
          step={10}
          value={draft.per_source_limit}
          onChange={(event) => update({ per_source_limit: Number(event.target.value) })}
        />

        <label className="source-toggle">
          <input type="checkbox" checked={draft.remote_only} onChange={(event) => update({ remote_only: event.target.checked })} />
          Только удалённая работа
        </label>

        {error && <p className="field-error" role="alert">{error}</p>}

        <button className="solid-action wide-action" type="submit" disabled={saving}>
          <Settings2 size={18} />{saving ? 'Сохраняю…' : 'Сохранить настройки'}
        </button>
      </form>
    </div>
  )
}
