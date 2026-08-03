import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileText,
  ListChecks,
  Plus,
  SquarePen,
  Sparkles,
  Target,
  Trash2,
  X,
} from 'lucide-react'
import { MetricCard, SidePanel } from '../components/DashboardUi'
import PageGuide from '../components/PageGuide'
import { SCHEDULE_GUIDE } from '../guides'
import AiWeekPlannerModal from './AiWeekPlannerModal'

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
  const [taskModal, setTaskModal] = useState<{ date: string; task: Task | null } | null>(null)
  const [showGoalModal, setShowGoalModal] = useState(false)
  const [showAiPlanner, setShowAiPlanner] = useState(false)
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
  const openCreateTask = (date = selectedDate >= weekStart && selectedDate <= addDays(weekStart, 6) ? selectedDate : weekStart) => {
    setSelectedDate(date)
    setTaskModal({ date, task: null })
  }
  const openEditTask = (task: Task) => {
    setSelectedDate(task.date)
    setTaskModal({ date: task.date, task })
  }
  const taskSaved = async (task: Task, mode: 'created' | 'updated') => {
    setTaskModal(null)
    const target = mondayOf(task.date)
    if (target !== weekStart) {
      setWeekStart(target)
      setSelectedDate(task.date)
    } else {
      await loadSchedule()
    }
    setNotice(mode === 'created' ? 'Задача добавлена' : 'Задача обновлена')
    window.setTimeout(() => setNotice(''), 2200)
  }
  const taskDeleted = async () => {
    setTaskModal(null)
    await loadSchedule()
    setNotice('Задача удалена')
    window.setTimeout(() => setNotice(''), 2200)
  }

  return (
    <div className="data-page schedule-page">
      <div className="schedule-grid">
        <section className="schedule-main">
          <header className="page-title-block"><h1>Расписание по дням</h1><p>Планируйте неделю, фиксируйте результаты и анализируйте прогресс</p></header>

          <PageGuide
            sectionId="schedule"
            title="Как пользоваться разделом «Расписание по дням»"
            intro="Неделя из семи колонок: задачи и встречи по дням, заметки, цели и итоги недели."
            steps={SCHEDULE_GUIDE}
          />

          <div className="schedule-controls">
            <div className="week-switcher" data-guide="schedule-week">
              <button type="button" aria-label="Предыдущая неделя" onClick={() => changeWeek(-1)}><ChevronLeft /></button>
              <strong>{formatWeek(weekStart)}</strong>
              <button type="button" aria-label="Следующая неделя" onClick={() => changeWeek(1)}><ChevronRight /></button>
              <button className="today-button" type="button" onClick={goToday}><CalendarDays size={16} />Сегодня</button>
            </div>
            <div className="schedule-control-actions">
              <button className="ai-schedule-action" type="button" data-guide="schedule-ai-plan" onClick={() => setShowAiPlanner(true)}><Sparkles size={18} />Составить неделю с ИИ</button>
              <button className="solid-action" type="button" data-guide="schedule-add" onClick={() => openCreateTask()}><Plus size={19} />Добавить задачу</button>
            </div>
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
            <div className="week-board">{days.map((day) => <WeekColumn day={day} onCreate={openCreateTask} onEdit={openEditTask} onToggle={toggleTask} onSaveNote={saveNote} key={day.date} />)}</div>
            <div className="schedule-bottom-grid">
              <section className="summary-panel">
                <div className="summary-panel-title"><div><h2>Итоги недели</h2><p>Подведите итоги недели: успехи, проблемы, идеи и выводы</p></div><span>{summary.length} / 2000</span></div>
                <textarea value={summary} onChange={(event) => setSummary(event.target.value)} aria-label="Итоги недели" placeholder="Запишите, что получилось и что важно улучшить…" />
                <button className="solid-action save-summary" type="button" onClick={() => void saveWeek()} disabled={saving}><Check size={18} />{saving ? 'Сохраняем…' : 'Сохранить итоги недели'}</button>
              </section>
              <section className="goals-panel" data-guide="schedule-goals">
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
          <SidePanel className="quick-actions-panel"><h2>Быстрые действия</h2><div><button type="button" onClick={() => openCreateTask()}><CheckCircle2 />Добавить задачу</button><button type="button" onClick={() => { setSelectedDate(todayIso()); document.querySelector('.day-note textarea')?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}><FileText />Добавить заметку дня</button></div></SidePanel>
        </aside>
      </div>
      {notice && <div className="schedule-toast" role="status">{notice}</div>}
      {taskModal && <TaskModal defaultDate={taskModal.date} task={taskModal.task} onClose={() => setTaskModal(null)} onSaved={taskSaved} onDeleted={taskDeleted} />}
      {showGoalModal && <GoalModal onClose={() => setShowGoalModal(false)} onCreated={async (title) => { await addGoal(title); setShowGoalModal(false) }} />}
      {showAiPlanner && <AiWeekPlannerModal weekStart={weekStart} weekEnd={addDays(weekStart, 6)} goals={data?.goals ?? []} onClose={() => setShowAiPlanner(false)} onApplied={async (createdCount, skippedCount) => {
        setShowAiPlanner(false)
        await loadSchedule()
        const createdText = createdCount === 1 ? 'Добавлена 1 задача' : `Добавлено ${createdCount} задач`
        setNotice(skippedCount ? `${createdText}, пропущено дублей: ${skippedCount}` : createdText)
        window.setTimeout(() => setNotice(''), 2200)
      }} />}
    </div>
  )
}

function WeekColumn({ day, onCreate, onEdit, onToggle, onSaveNote }: { day: { date: string; short: string; tasks: Task[]; note: string }; onCreate: (date: string) => void; onEdit: (task: Task) => void; onToggle: (task: Task) => Promise<void>; onSaveNote: (date: string, note: string) => Promise<void> }) {
  const [draft, setDraft] = useState(day.note)
  const [saving, setSaving] = useState(false)
  const shortDate = parseDate(day.date).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
  useEffect(() => setDraft(day.note), [day.note])
  const save = async () => { setSaving(true); await onSaveNote(day.date, draft); setSaving(false) }
  return <article className="week-column"><header><button className="day-add-button" type="button" onClick={() => onCreate(day.date)} aria-label={`Добавить задачу на ${day.short} ${shortDate}`}><strong>{day.short}</strong><span>{shortDate}</span><b>{day.tasks.length}</b><Plus size={14} aria-hidden="true" /></button></header><div className="day-task-list">{day.tasks.length ? <>{day.tasks.map((task) => <div className={`day-task ${task.done ? 'done' : ''}`} key={task.id}><button className="task-toggle" type="button" onClick={() => void onToggle(task)} aria-label={task.done ? `Отметить задачу «${task.title}» невыполненной` : `Отметить задачу «${task.title}» выполненной`}><span className="task-check" aria-hidden="true">{task.done && <Check size={12} />}</span></button><button className="task-edit" type="button" onClick={() => onEdit(task)} aria-label={`Редактировать задачу ${task.title}`}><span><strong>{task.title}</strong>{task.time && <small>{task.time}{task.kind === 'meeting' ? ' · встреча' : ''}</small>}</span><SquarePen size={13} aria-hidden="true" /></button></div>)}<button className="day-add-inline" type="button" onClick={() => onCreate(day.date)} aria-label={`Добавить ещё задачу на ${day.short} ${shortDate}`}><Plus size={13} />Добавить</button></> : <button className="day-empty day-empty-action" type="button" onClick={() => onCreate(day.date)} aria-label={`Создать первую задачу на ${day.short} ${shortDate}`}><Plus size={14} />Задач нет — добавить</button>}</div><div className="day-note" data-guide="schedule-note"><small>Заметка дня</small><textarea value={draft} onChange={(event) => setDraft(event.target.value)} aria-label={`Заметка ${day.date}`} placeholder="Что произошло сегодня?" /><button type="button" onClick={() => void save()} disabled={saving || draft === day.note}><Plus size={13} />{saving ? 'Сохраняем…' : 'Сохранить заметку'}</button></div></article>
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

function TaskModal({ defaultDate, task, onClose, onSaved, onDeleted }: { defaultDate: string; task: Task | null; onClose: () => void; onSaved: (task: Task, mode: 'created' | 'updated') => Promise<void>; onDeleted: () => Promise<void> }) {
  const [title, setTitle] = useState(task?.title ?? '')
  const [taskDate, setTaskDate] = useState(task?.date ?? defaultDate)
  const [taskTime, setTaskTime] = useState(task?.time ?? '')
  const [kind, setKind] = useState<TaskKind>(task?.kind ?? 'task')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<'save' | 'delete' | ''>('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const isEditing = task !== null
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy('save')
    setError('')
    try {
      const savedTask = await apiRequest<Task>(isEditing ? `/api/schedule/tasks/${task.id}` : '/api/schedule/tasks', { method: isEditing ? 'PUT' : 'POST', body: JSON.stringify({ title: title.trim(), task_date: taskDate, task_time: taskTime, kind }) })
      await onSaved(savedTask, isEditing ? 'updated' : 'created')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : isEditing ? 'Не удалось сохранить задачу' : 'Не удалось добавить задачу')
    } finally { setBusy('') }
  }
  const remove = async () => {
    if (!task) return
    setBusy('delete')
    setError('')
    try {
      await apiRequest(`/api/schedule/tasks/${task.id}`, { method: 'DELETE' })
      await onDeleted()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось удалить задачу')
      setBusy('')
    }
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal schedule-task-modal" role="dialog" aria-modal="true" aria-labelledby="schedule-task-modal-title" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className={`metric-icon ${isEditing ? 'purple' : 'blue'}`}>{isEditing ? <SquarePen /> : <CheckCircle2 />}</span><h2 id="schedule-task-modal-title">{isEditing ? 'Редактирование задачи' : 'Новая задача'}</h2><label htmlFor="task-title">Название задачи</label><input id="task-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, подготовить отчёт" required /><label htmlFor="task-date">Дата</label><input id="task-date" type="date" value={taskDate} onChange={(event) => setTaskDate(event.target.value)} required /><div className="schedule-modal-fields"><label htmlFor="task-time">Время<input id="task-time" type="time" value={taskTime} onChange={(event) => setTaskTime(event.target.value)} /></label><label htmlFor="task-kind">Тип<select id="task-kind" value={kind} onChange={(event) => setKind(event.target.value as TaskKind)}><option value="task">Задача</option><option value="meeting">Встреча</option></select></label></div>{error && <p className="form-error" role="alert">{error}</p>}{isEditing && confirmDelete && <div className="task-delete-confirm"><p>Удалить задачу без возможности восстановления?</p><div><button type="button" onClick={() => setConfirmDelete(false)} disabled={Boolean(busy)}>Отмена</button><button className="danger-action" type="button" onClick={() => void remove()} disabled={Boolean(busy)} aria-label="Подтвердить удаление задачи"><Trash2 size={16} />{busy === 'delete' ? 'Удаляем…' : 'Удалить'}</button></div></div>}{!confirmDelete && <div className="task-modal-actions">{isEditing && <button className="task-delete-button" type="button" onClick={() => setConfirmDelete(true)} disabled={Boolean(busy)}><Trash2 size={17} />Удалить задачу</button>}<button className="solid-action" type="submit" disabled={!title.trim() || Boolean(busy)}>{isEditing ? <Check size={18} /> : <Plus size={18} />}{busy === 'save' ? 'Сохраняем…' : isEditing ? 'Сохранить изменения' : 'Добавить задачу'}</button></div>}</form></div>
}

function GoalModal({ onClose, onCreated }: { onClose: () => void; onCreated: (title: string) => Promise<void> }) {
  const [title, setTitle] = useState('')
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal" onSubmit={(event) => { event.preventDefault(); if (title.trim()) void onCreated(title.trim()) }} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className="metric-icon orange"><Target /></span><h2>Новая цель</h2><label htmlFor="goal-title">Цель недели</label><input id="goal-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, провести 3 встречи" required /><button className="solid-action wide-action" type="submit" disabled={!title.trim()}><Plus size={18} />Добавить цель</button></form></div>
}
