import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  ListChecks,
  Plus,
  Target,
  X,
} from 'lucide-react'
import { MetricCard, SidePanel } from '../components/DashboardUi'

type TaskKind = 'task' | 'meeting'
type Task = { id: number; date: string; title: string; time: string; kind: TaskKind; done: boolean }
type Goal = { title: string; done: boolean }
type ScheduleData = {
  week_start: string
  week_end: string
  tasks: Task[]
  notes: Record<string, string>
  summary: string
  goals: Goal[]
  focus: string
  stats: { total: number; done: number; meetings: number; completion_percent: number }
  upcoming: Task[]
  past_weeks: string[]
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000'
const ruWeekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const ruDate = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
const ruMonth = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' })

function pad(value: number) { return String(value).padStart(2, '0') }
function isoDate(value: Date) { return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}` }
function parseDate(value: string) {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}
function addDays(value: string, amount: number) {
  const date = parseDate(value)
  date.setDate(date.getDate() + amount)
  return isoDate(date)
}
function mondayOf(value: string) {
  const date = parseDate(value)
  const shift = (date.getDay() + 6) % 7
  date.setDate(date.getDate() - shift)
  return isoDate(date)
}
function todayIso() { return isoDate(new Date()) }
function formatDay(value: string) { return ruDate.format(parseDate(value)) }
function formatWeek(value: string) {
  const end = parseDate(addDays(value, 6))
  const start = parseDate(value)
  return `Неделя ${start.getDate()}–${end.getDate()} ${new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(end)}`
}
function formatPastWeek(value: string) {
  const end = parseDate(addDays(value, 6))
  const monthStart = new Intl.DateTimeFormat('ru-RU', { month: 'long' }).format(parseDate(value))
  const monthEnd = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(end)
  return `${parseDate(value).getDate()}–${end.getDate()} ${monthStart === new Intl.DateTimeFormat('ru-RU', { month: 'long' }).format(end) ? monthEnd : `${monthStart} – ${monthEnd}`}`
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Не удалось сохранить изменения')
  return body as T
}

export default function SchedulePage() {
  const [weekStart, setWeekStart] = useState(() => mondayOf(todayIso()))
  const [selectedDate, setSelectedDate] = useState(() => todayIso())
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const date = new Date()
    return new Date(date.getFullYear(), date.getMonth(), 1)
  })
  const [data, setData] = useState<ScheduleData | null>(null)
  const [summary, setSummary] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [showGoalModal, setShowGoalModal] = useState(false)
  const [notice, setNotice] = useState('')

  const loadSchedule = async (targetWeek = weekStart) => {
    setLoading(true)
    setError('')
    try {
      const result = await apiRequest<ScheduleData>(`/api/schedule?week_start=${targetWeek}`)
      setData(result)
      setSummary(result.summary)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить расписание')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadSchedule() }, [weekStart])

  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => {
    const date = addDays(weekStart, index)
    return {
      date,
      short: ruWeekdays[index],
      tasks: data?.tasks.filter((task) => task.date === date) ?? [],
      note: data?.notes[date] ?? '',
    }
  }), [data, weekStart])

  const changeWeek = (offset: number) => {
    const next = addDays(weekStart, offset * 7)
    setWeekStart(next)
    setSelectedDate(next)
    setCalendarMonth(new Date(parseDate(next).getFullYear(), parseDate(next).getMonth(), 1))
  }
  const goToday = () => {
    const today = todayIso()
    setWeekStart(mondayOf(today))
    setSelectedDate(today)
    setCalendarMonth(new Date(parseDate(today).getFullYear(), parseDate(today).getMonth(), 1))
  }
  const selectDate = (date: string) => {
    setSelectedDate(date)
    setWeekStart(mondayOf(date))
    setCalendarMonth(new Date(parseDate(date).getFullYear(), parseDate(date).getMonth(), 1))
  }

  const toggleTask = async (task: Task) => {
    try {
      await apiRequest(`/api/schedule/tasks/${task.id}`, { method: 'PUT', body: JSON.stringify({ done: !task.done }) })
      await loadSchedule()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось обновить задачу')
    }
  }
  const saveNote = async (date: string, note: string) => {
    try {
      await apiRequest(`/api/schedule/notes/${date}`, { method: 'PUT', body: JSON.stringify({ note }) })
      await loadSchedule()
      setNotice('Заметка сохранена')
      window.setTimeout(() => setNotice(''), 2200)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось сохранить заметку')
    }
  }
  const saveWeek = async (nextGoals = data?.goals ?? []) => {
    setSaving(true)
    try {
      const result = await apiRequest<ScheduleData>(`/api/schedule/weeks/${weekStart}`, {
        method: 'PUT',
        body: JSON.stringify({ summary, goals: nextGoals, focus: data?.focus ?? '' }),
      })
      setData((current) => current ? { ...current, summary: result.summary, goals: result.goals, focus: result.focus } : current)
      setNotice('Изменения сохранены')
      window.setTimeout(() => setNotice(''), 2200)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось сохранить итоги недели')
    } finally {
      setSaving(false)
    }
  }
  const addGoal = async (title: string) => {
    const nextGoals = [...(data?.goals ?? []), { title, done: false }]
    await saveWeek(nextGoals)
  }
  const toggleGoal = async (index: number) => {
    const nextGoals = (data?.goals ?? []).map((goal, goalIndex) => goalIndex === index ? { ...goal, done: !goal.done } : goal)
    await saveWeek(nextGoals)
  }
  const taskCreated = async (task: Task) => {
    setShowTaskModal(false)
    const target = mondayOf(task.date)
    if (target !== weekStart) {
      setWeekStart(target)
      setSelectedDate(task.date)
    } else {
      await loadSchedule()
    }
    setNotice('Задача добавлена')
    window.setTimeout(() => setNotice(''), 2200)
  }

  return (
    <div className="data-page schedule-page">
      <div className="schedule-grid">
        <section className="schedule-main">
          <header className="page-title-block"><h1>Расписание по дням</h1><p>Планируйте неделю, фиксируйте результаты и анализируйте прогресс</p></header>
          <div className="schedule-controls">
            <div className="week-switcher">
              <button type="button" aria-label="Предыдущая неделя" onClick={() => changeWeek(-1)}><ChevronLeft /></button>
              <strong>{formatWeek(weekStart)}</strong>
              <button type="button" aria-label="Следующая неделя" onClick={() => changeWeek(1)}><ChevronRight /></button>
              <button className="today-button" type="button" onClick={goToday}><CalendarDays size={16} />Сегодня</button>
            </div>
            <button className="solid-action" type="button" onClick={() => setShowTaskModal(true)}><Plus size={19} />Добавить задачу</button>
          </div>
          {loading && <div className="schedule-loading" role="status">Загружаем сохранённое расписание…</div>}
          {error && <div className="schedule-error" role="alert">{error}<button type="button" onClick={() => void loadSchedule()}>Повторить</button></div>}
          {!loading && data && <>
            <div className="metrics-grid schedule-metrics">
              <MetricCard icon={ListChecks} label="Задач на неделю" value={data.stats.total} hint="Только сохранённые задачи" accent="blue" />
              <MetricCard icon={CheckCircle2} label="Выполнено" value={data.stats.done} hint={`${data.stats.completion_percent}% от плана`} accent="green" />
              <MetricCard icon={CalendarDays} label="Важные встречи" value={data.stats.meetings} hint="Встречи в этой неделе" accent="purple" />
              <MetricCard icon={Target} label="Фокус недели" value={data.focus || '—'} hint={data.focus ? 'Сохранённый фокус' : 'Фокус пока не задан'} accent="orange" />
            </div>
            <div className="week-board">{days.map((day) => <WeekColumn day={day} onToggle={toggleTask} onSaveNote={saveNote} key={day.date} />)}</div>
            <div className="schedule-bottom-grid">
              <section className="summary-panel">
                <div className="summary-panel-title"><div><h2>Итоги недели</h2><p>Подведите итоги недели: успехи, проблемы, идеи и выводы</p></div><span>{summary.length} / 2000</span></div>
                <textarea value={summary} onChange={(event) => setSummary(event.target.value)} aria-label="Итоги недели" placeholder="Запишите, что получилось и что важно улучшить…" />
                <button className="solid-action save-summary" type="button" onClick={() => void saveWeek()} disabled={saving}><Check size={18} />{saving ? 'Сохраняем…' : 'Сохранить итоги недели'}</button>
              </section>
              <section className="goals-panel">
                <div className="summary-panel-title"><h2>Цели на неделю</h2><button type="button" onClick={() => setShowGoalModal(true)}>Добавить</button></div>
                <div className="goal-list">
                  {data.goals.length === 0 && <p className="goal-empty">Целей пока нет. Добавьте первую цель недели.</p>}
                  {data.goals.map((goal, index) => <button type="button" className="goal-row" key={`${goal.title}-${index}`} onClick={() => void toggleGoal(index)}><span className={`goal-check ${goal.done ? 'done' : ''}`}>{goal.done && <Check size={12} />}</span><span>{goal.title}</span><span className="drag-handle" aria-hidden="true">⋮⋮</span></button>)}
                </div>
              </section>
            </div>
          </>}
        </section>
        <aside className="schedule-side-column">
          <SidePanel className="calendar-panel"><div className="calendar-title-row"><h2>Календарь</h2></div><div className="month-switcher"><button type="button" aria-label="Предыдущий месяц" onClick={() => setCalendarMonth((value) => new Date(value.getFullYear(), value.getMonth() - 1, 1))}><ChevronLeft /></button><strong>{ruMonth.format(calendarMonth)} <ChevronDownSmall /></strong><button type="button" aria-label="Следующий месяц" onClick={() => setCalendarMonth((value) => new Date(value.getFullYear(), value.getMonth() + 1, 1))}><ChevronRight /></button></div><CalendarGrid month={calendarMonth} selectedDate={selectedDate} weekStart={weekStart} onSelect={selectDate} /></SidePanel>
          <SidePanel className="upcoming-panel"><div className="side-panel-title-row"><h2>Ближайшие события</h2></div>{data?.upcoming.length ? <div className="upcoming-list">{data.upcoming.map((task) => <div key={task.id}><p><strong>{formatDay(task.date)}</strong><b>{task.time || 'Весь день'}</b></p><span className={task.kind === 'meeting' ? 'purple' : 'blue'} /><div><strong>{task.title}</strong><small>{task.kind === 'meeting' ? 'Встреча' : 'Задача'}</small></div></div>)}</div> : <p className="side-empty">Сохранённых ближайших событий нет.</p>}</SidePanel>
          <SidePanel className="past-panel"><h2>Прошлые недели</h2>{data?.past_weeks.length ? data.past_weeks.map((pastWeek) => <button type="button" key={pastWeek} onClick={() => { setWeekStart(pastWeek); setSelectedDate(pastWeek) }}>{formatPastWeek(pastWeek)}<ChevronRight size={15} /></button>) : <p className="side-empty">Истории прошлых недель пока нет.</p>}<button className="archive-button" type="button" onClick={() => setNotice('Архив появится после сохранения первой недели')}>Открыть архив</button></SidePanel>
          <SidePanel className="quick-actions-panel"><h2>Быстрые действия</h2><div><button type="button" onClick={() => setShowTaskModal(true)}><CheckCircle2 />Добавить задачу</button><button type="button" onClick={() => { setSelectedDate(todayIso()); document.querySelector('.day-note textarea')?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}><FileText />Добавить заметку дня</button></div></SidePanel>
        </aside>
      </div>
      {notice && <div className="schedule-toast" role="status">{notice}</div>}
      {showTaskModal && <TaskModal defaultDate={selectedDate >= weekStart && selectedDate <= addDays(weekStart, 6) ? selectedDate : weekStart} onClose={() => setShowTaskModal(false)} onCreated={taskCreated} />}
      {showGoalModal && <GoalModal onClose={() => setShowGoalModal(false)} onCreated={async (title) => { await addGoal(title); setShowGoalModal(false) }} />}
    </div>
  )
}

function WeekColumn({ day, onToggle, onSaveNote }: { day: { date: string; short: string; tasks: Task[]; note: string }; onToggle: (task: Task) => Promise<void>; onSaveNote: (date: string, note: string) => Promise<void> }) {
  const [draft, setDraft] = useState(day.note)
  const [saving, setSaving] = useState(false)
  useEffect(() => setDraft(day.note), [day.note])
  const save = async () => { setSaving(true); await onSaveNote(day.date, draft); setSaving(false) }
  return <article className="week-column"><header><strong>{day.short}</strong><span>{parseDate(day.date).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}</span><b>{day.tasks.length}</b></header><div className="day-task-list">{day.tasks.length ? day.tasks.map((task) => <button type="button" className={`day-task ${task.done ? 'done' : ''}`} key={task.id} onClick={() => void onToggle(task)}><span className="task-check" aria-hidden="true">{task.done && <Check size={12} />}</span><span><strong>{task.title}</strong>{task.time && <small>{task.time}{task.kind === 'meeting' ? ' · встреча' : ''}</small>}</span></button>) : <p className="day-empty">Задач нет</p>}</div><div className="day-note"><small>Заметка дня</small><textarea value={draft} onChange={(event) => setDraft(event.target.value)} aria-label={`Заметка ${day.date}`} placeholder="Что произошло сегодня?" /><button type="button" onClick={() => void save()} disabled={saving || draft === day.note}><Plus size={13} />{saving ? 'Сохраняем…' : 'Сохранить заметку'}</button></div></article>
}

function CalendarGrid({ month, selectedDate, weekStart, onSelect }: { month: Date; selectedDate: string; weekStart: string; onSelect: (date: string) => void }) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const mondayOffset = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(first.getDate() - mondayOffset)
  const cells = Array.from({ length: 42 }, (_, index) => { const date = new Date(start); date.setDate(start.getDate() + index); return date })
  return <div className="mini-calendar"><div className="calendar-weekdays">{ruWeekdays.map((item) => <span key={item}>{item}</span>)}</div><div className="calendar-cells">{cells.map((date) => { const value = isoDate(date); const inMonth = date.getMonth() === month.getMonth(); const inWeek = value >= weekStart && value <= addDays(weekStart, 6); return <button type="button" key={value} className={`${inMonth ? '' : 'muted'} ${inWeek ? 'selected-week-day' : ''} ${value === selectedDate ? 'selected-day' : ''}`} onClick={() => onSelect(value)}>{date.getDate()}</button> })}</div></div>
}

function ChevronDownSmall() { return <ChevronRight className="chevron-down" size={14} /> }

function TaskModal({ defaultDate, onClose, onCreated }: { defaultDate: string; onClose: () => void; onCreated: (task: Task) => Promise<void> }) {
  const [title, setTitle] = useState('')
  const [taskDate, setTaskDate] = useState(defaultDate)
  const [taskTime, setTaskTime] = useState('')
  const [kind, setKind] = useState<TaskKind>('task')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const task = await apiRequest<Task>('/api/schedule/tasks', { method: 'POST', body: JSON.stringify({ title: title.trim(), task_date: taskDate, task_time: taskTime, kind }) })
      await onCreated(task)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось добавить задачу')
    } finally { setSaving(false) }
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal schedule-task-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className="metric-icon blue"><CheckCircle2 /></span><h2>Новая задача</h2><label htmlFor="task-title">Название задачи</label><input id="task-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, подготовить отчёт" required /><label htmlFor="task-date">Дата</label><input id="task-date" type="date" value={taskDate} onChange={(event) => setTaskDate(event.target.value)} required /><div className="schedule-modal-fields"><label htmlFor="task-time">Время<input id="task-time" type="time" value={taskTime} onChange={(event) => setTaskTime(event.target.value)} /></label><label htmlFor="task-kind">Тип<select id="task-kind" value={kind} onChange={(event) => setKind(event.target.value as TaskKind)}><option value="task">Задача</option><option value="meeting">Встреча</option></select></label></div>{error && <p className="form-error">{error}</p>}<button className="solid-action wide-action" type="submit" disabled={!title.trim() || saving}><Plus size={18} />{saving ? 'Добавляем…' : 'Добавить задачу'}</button></form></div>
}

function GoalModal({ onClose, onCreated }: { onClose: () => void; onCreated: (title: string) => Promise<void> }) {
  const [title, setTitle] = useState('')
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal" onSubmit={(event) => { event.preventDefault(); if (title.trim()) void onCreated(title.trim()) }} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className="metric-icon orange"><Target /></span><h2>Новая цель</h2><label htmlFor="goal-title">Цель недели</label><input id="goal-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, провести 3 встречи" required /><button className="solid-action wide-action" type="submit" disabled={!title.trim()}><Plus size={18} />Добавить цель</button></form></div>
}
