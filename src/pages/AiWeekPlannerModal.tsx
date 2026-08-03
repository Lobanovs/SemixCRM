import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  ArrowLeft,
  CalendarClock,
  Check,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react'

import { apiRequest } from '../api'

type Intensity = 'light' | 'balanced' | 'intensive'
type Goal = { title: string; done: boolean }
type AiDraftTask = {
  id: string
  date: string
  time: string
  title: string
  kind: 'task' | 'meeting'
  reason: string
}
type AiWeekPlan = {
  week_start: string
  week_end: string
  focus: string
  summary: string
  tasks: AiDraftTask[]
}
type ApplyResponse = {
  created_count: number
  skipped_count: number
}

type Props = {
  weekStart: string
  weekEnd: string
  goals: Goal[]
  onClose: () => void
  onApplied: (createdCount: number, skippedCount: number) => Promise<void>
}

const dayFormatter = new Intl.DateTimeFormat('ru-RU', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
})
const shortDateFormatter = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' })

function parseIso(value: string) {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function formatDay(value: string) {
  const formatted = dayFormatter.format(parseIso(value))
  return formatted.slice(0, 1).toUpperCase() + formatted.slice(1)
}

function initialObjective(goals: Goal[]) {
  return goals.filter((goal) => !goal.done).map((goal) => goal.title.trim()).filter(Boolean).join('; ')
}

export default function AiWeekPlannerModal({ weekStart, weekEnd, goals, onClose, onApplied }: Props) {
  const [objective, setObjective] = useState(() => initialObjective(goals))
  const [intensity, setIntensity] = useState<Intensity>('balanced')
  const [includeWeekend, setIncludeWeekend] = useState(false)
  const [plan, setPlan] = useState<AiWeekPlan | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState<'generate' | 'apply' | ''>('')
  const [error, setError] = useState('')

  const selectedTasks = useMemo(
    () => plan?.tasks.filter((task) => selectedIds.has(task.id)) ?? [],
    [plan, selectedIds],
  )
  const taskGroups = useMemo(() => {
    const grouped = new Map<string, AiDraftTask[]>()
    for (const task of plan?.tasks ?? []) {
      grouped.set(task.date, [...(grouped.get(task.date) ?? []), task])
    }
    return [...grouped.entries()]
  }, [plan])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [busy, onClose])

  const generate = async (event?: FormEvent) => {
    event?.preventDefault()
    if (!objective.trim()) return
    setBusy('generate')
    setError('')
    try {
      const result = await apiRequest<AiWeekPlan>('/api/ai/schedule/plan', {
        method: 'POST',
        body: {
          week_start: weekStart,
          objective: objective.trim(),
          intensity,
          include_weekend: includeWeekend,
        },
        fallback: 'Не удалось составить план недели',
      })
      setPlan(result)
      setSelectedIds(new Set(result.tasks.map((task) => task.id)))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось составить план недели')
    } finally {
      setBusy('')
    }
  }

  const apply = async () => {
    if (!plan || selectedTasks.length === 0) return
    setBusy('apply')
    setError('')
    try {
      const result = await apiRequest<ApplyResponse>('/api/ai/schedule/plan/apply', {
        method: 'POST',
        body: {
          week_start: weekStart,
          focus: plan.focus,
          tasks: selectedTasks.map(({ id: _id, ...task }) => task),
        },
        fallback: 'Не удалось добавить задачи в расписание',
      })
      await onApplied(result.created_count, result.skipped_count)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось добавить задачи в расписание')
      setBusy('')
    }
  }

  const toggleTask = (taskId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }

  const close = () => {
    if (!busy) onClose()
  }

  return (
    <div className="modal-backdrop ai-week-planner-backdrop" role="presentation" onMouseDown={close}>
      <section
        className="ai-week-planner-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-week-planner-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="ai-week-planner-header">
          <div className="ai-week-planner-heading">
            <span className="ai-week-planner-icon" aria-hidden="true"><Sparkles size={21} /></span>
            <div>
              <span className="ai-week-planner-eyebrow">OpenCode Go · черновик</span>
              <h2 id="ai-week-planner-title">ИИ-планировщик недели</h2>
              <p>{shortDateFormatter.format(parseIso(weekStart))} — {shortDateFormatter.format(parseIso(weekEnd))}</p>
            </div>
          </div>
          <button className="ai-week-planner-close" type="button" onClick={close} disabled={Boolean(busy)} aria-label="Закрыть ИИ-планировщик"><X size={20} /></button>
        </header>

        {!plan ? (
          <form className="ai-week-planner-brief" onSubmit={(event) => void generate(event)}>
            <div className="ai-week-planner-intro">
              <CalendarClock size={20} aria-hidden="true" />
              <div><strong>Сначала задайте результат</strong><p>ИИ учтёт сохранённые задачи и цели. Ничего не попадёт в расписание без вашего подтверждения.</p></div>
            </div>

            <div className="ai-week-planner-field">
              <label htmlFor="ai-week-objective">Главный результат недели</label>
              <textarea
                id="ai-week-objective"
                autoFocus
                value={objective}
                onChange={(event) => setObjective(event.target.value)}
                placeholder="Например: закончить лендинг и подготовить его к запуску"
                maxLength={1200}
                required
              />
              <small>Опишите результат своими словами — ИИ разобьёт его на выполнимые шаги.</small>
            </div>

            <fieldset className="ai-week-planner-intensity">
              <legend>Нагрузка</legend>
              {([
                ['light', 'Лёгкая', 'До 7 задач'],
                ['balanced', 'Сбалансированная', 'До 12 задач'],
                ['intensive', 'Интенсивная', 'До 16 задач'],
              ] as const).map(([value, title, hint]) => (
                <label key={value} className={intensity === value ? 'selected' : ''}>
                  <input type="radio" name="ai-week-intensity" value={value} checked={intensity === value} onChange={() => setIntensity(value)} />
                  <span><strong>{title}</strong><small>{hint}</small></span>
                  {intensity === value && <Check size={16} aria-hidden="true" />}
                </label>
              ))}
            </fieldset>

            <label className="ai-week-planner-weekend">
              <input type="checkbox" checked={includeWeekend} onChange={(event) => setIncludeWeekend(event.target.checked)} />
              <span><strong>Планировать задачи на выходные</strong><small>По умолчанию суббота и воскресенье остаются свободными.</small></span>
            </label>

            {error && <div className="ai-week-planner-error" role="alert">{error}</div>}
            {busy === 'generate' && <p className="ai-week-planner-status" role="status"><LoaderCircle className="spin" size={17} />ИИ анализирует цели и свободные дни…</p>}

            <footer className="ai-week-planner-footer">
              <button className="ai-week-planner-secondary" type="button" onClick={close} disabled={Boolean(busy)}>Отмена</button>
              <button className="solid-action" type="submit" disabled={!objective.trim() || Boolean(busy)}><Sparkles size={18} />{busy === 'generate' ? 'Составляем…' : 'Составить черновик'}</button>
            </footer>
          </form>
        ) : (
          <div className="ai-week-planner-preview">
            <div className="ai-week-plan-summary">
              <span>Фокус недели</span>
              <h3>{plan.focus}</h3>
              <p>{plan.summary}</p>
            </div>

            <div className="ai-week-plan-toolbar">
              <div><strong>{selectedTasks.length} из {plan.tasks.length}</strong><span> задач будут добавлены</span></div>
              <button type="button" onClick={() => setSelectedIds(selectedIds.size === plan.tasks.length ? new Set() : new Set(plan.tasks.map((task) => task.id)))} disabled={Boolean(busy)}>
                {selectedIds.size === plan.tasks.length ? 'Снять выбор' : 'Выбрать все'}
              </button>
            </div>

            <div className="ai-week-plan-days">
              {taskGroups.map(([taskDate, tasks]) => (
                <section className="ai-week-plan-day" key={taskDate}>
                  <header><strong>{formatDay(taskDate)}</strong><span>{tasks.length}</span></header>
                  <div>
                    {tasks.map((task) => (
                      <label className={`ai-week-plan-task ${selectedIds.has(task.id) ? 'selected' : ''}`} key={task.id}>
                        <input type="checkbox" checked={selectedIds.has(task.id)} onChange={() => toggleTask(task.id)} aria-label={`Добавить задачу «${task.title}»`} />
                        <span className="ai-week-plan-check" aria-hidden="true">{selectedIds.has(task.id) && <Check size={13} />}</span>
                        <span className="ai-week-plan-task-copy">
                          <span><strong>{task.title}</strong>{task.time && <time>{task.time}</time>}</span>
                          <small>{task.reason}</small>
                        </span>
                      </label>
                    ))}
                  </div>
                </section>
              ))}
            </div>

            {error && <div className="ai-week-planner-error" role="alert">{error}</div>}
            {busy === 'apply' && <p className="ai-week-planner-status" role="status"><LoaderCircle className="spin" size={17} />Добавляем выбранные задачи…</p>}

            <footer className="ai-week-planner-footer ai-week-planner-preview-footer">
              <button className="ai-week-planner-secondary" type="button" onClick={() => { setPlan(null); setError('') }} disabled={Boolean(busy)}><ArrowLeft size={17} />Назад к цели</button>
              <button className="ai-week-planner-secondary" type="button" onClick={() => void generate()} disabled={Boolean(busy)}><RefreshCw size={17} />Составить заново</button>
              <button className="solid-action" type="button" onClick={() => void apply()} disabled={selectedTasks.length === 0 || Boolean(busy)}><Check size={18} />{busy === 'apply' ? 'Добавляем…' : `Добавить ${selectedTasks.length} ${selectedTasks.length === 1 ? 'задачу' : 'задач'}`}</button>
            </footer>
          </div>
        )}
      </section>
    </div>
  )
}
