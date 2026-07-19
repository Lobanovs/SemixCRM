import { useMemo, useState } from 'react'
import {
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Circle,
  Clock3,
  FileText,
  Lightbulb,
  ListChecks,
  MessageSquare,
  Plus,
  Target,
  UsersRound,
  X,
} from 'lucide-react'
import { MetricCard, SidePanel, StatusBadge } from '../components/DashboardUi'

type Task = { id: number; title: string; time: string; done: boolean; tone?: string }
type WeekDay = { short: string; date: string; count: number; tasks: Task[]; note: string }

const initialWeek: WeekDay[] = [
  { short: 'Пн', date: '20.07', count: 6, tasks: [{ id: 1, title: 'Стендап по проекту', time: '10:00', done: false }, { id: 2, title: 'Доработка задачи CRM для клиентов', time: '11:00', done: false }, { id: 3, title: 'Созвон с командой', time: '14:00', done: true }, { id: 4, title: 'Отправить отклики на вакансии (3)', time: '16:30', done: false }, { id: 5, title: 'Спорт: тренировка', time: '18:30', done: false }, { id: 6, title: 'Чтение: 30 мин перед сном', time: '', done: true }], note: 'Продуктивный день, закрыл важную задачу.' },
  { short: 'Вт', date: '21.07', count: 5, tasks: [{ id: 7, title: 'Анализ вакансий', time: '10:00', done: true }, { id: 8, title: 'Отклик: Product Manager (ООО «Тех»)', time: '11:30', done: false }, { id: 9, title: 'Созвон с фриланс-клиентом', time: '14:00', done: false }, { id: 10, title: 'Изучение Nest.js', time: '16:00', done: false }, { id: 11, title: 'Прогулка / спорт', time: '19:00', done: false }], note: 'Нашёл интересную вакансию, отправил отклик.' },
  { short: 'Ср', date: '22.07', count: 6, tasks: [{ id: 12, title: 'Планирование спринта', time: '10:00', done: false }, { id: 13, title: 'Работа над проектом', time: '12:00', done: true }, { id: 14, title: 'Встреча с заказчиком', time: '15:00', done: false }, { id: 15, title: 'Отклик: Frontend Developer', time: '16:30', done: false }, { id: 16, title: 'Изучение английского', time: '18:00', done: false }, { id: 17, title: 'Медитация / отдых', time: '21:00', done: false }], note: 'Обсудили ТЗ, получили новые правки.' },
  { short: 'Чт', date: '23.07', count: 5, tasks: [{ id: 18, title: 'Ревью кода', time: '10:00', done: true }, { id: 19, title: 'Доработка CRM', time: '12:00', done: false }, { id: 20, title: 'Созвон с фриланс-клиентом', time: '14:30', done: false }, { id: 21, title: 'Отклики на вакансии (2)', time: '16:00', done: false }, { id: 22, title: 'Чтение: 30 мин перед сном', time: '', done: true }], note: 'Сделал ревью, отправил ещё 2 отклика.' },
  { short: 'Пт', date: '24.07', count: 6, tasks: [{ id: 23, title: 'Ретро встречи', time: '10:00', done: false }, { id: 24, title: 'Подготовка отчёта', time: '12:00', done: true }, { id: 25, title: 'Созвон по вакансии', time: '14:00', done: false }, { id: 26, title: 'Портфолио: обновить кейс', time: '16:00', done: false }, { id: 27, title: 'Спорт: зал', time: '18:30', done: false }, { id: 28, title: 'Планирование на след. неделю', time: '20:30', done: false }], note: 'Отправил отчёт, получил позитивный фидбек.' },
  { short: 'Сб', date: '25.07', count: 4, tasks: [{ id: 29, title: 'Обучение: Next.js', time: '11:00', done: false }, { id: 30, title: 'Личный проект', time: '13:00', done: false }, { id: 31, title: 'Прогулка / спорт', time: '16:00', done: true }, { id: 32, title: 'Нетворкинг / чтение', time: '19:00', done: false }], note: 'Поработал над личным проектом, хорошая прогулка.' },
  { short: 'Вс', date: '26.07', count: 3, tasks: [{ id: 33, title: 'Планирование дня', time: '11:00', done: false }, { id: 34, title: 'Семья / отдых', time: '13:00', done: false }, { id: 35, title: 'Рефлексия недели', time: '18:00', done: true }], note: 'Отдохнул, подвёл итоги недели.' },
]

const upcoming = [
  ['Завтра, 21 июля', '10:00', 'Анализ вакансий', 'Поиск работы', 'blue'],
  ['22 июля', '15:00', 'Встреча с заказчиком', 'CRM для клиентов', 'purple'],
  ['24 июля', '14:00', 'Созвон по вакансии', 'Product Manager', 'green'],
  ['25 июля', '16:00', 'Спорт: зал', 'Личное', 'orange'],
] as const

export default function SchedulePage() {
  const [week, setWeek] = useState(initialWeek)
  const [selectedDate, setSelectedDate] = useState(20)
  const [summary, setSummary] = useState('• Успехи: завершил важную задачу по CRM, получил хороший фидбек по отчёту, отправил 7 откликов.\n• Проблемы: не хватало времени на обучение, несколько созвонов перенесли.\n• Идеи: автоматизировать отчёты, улучшить процесс онбординга клиентов.\n• Выводы: держать фокус на ключевых задачах, больше планировать.')
  const [goals, setGoals] = useState([
    { title: 'Завершить задачи по CRM', done: true },
    { title: 'Отправить не менее 7 откликов', done: true },
    { title: 'Обновить портфолио', done: true },
    { title: 'Изучить Next.js', done: false },
    { title: '3 тренировки', done: true, progress: '2 / 3' },
    { title: 'Читать 30 мин в день', done: true },
  ])
  const [showModal, setShowModal] = useState(false)

  const doneCount = useMemo(() => week.reduce((sum, day) => sum + day.tasks.filter((task) => task.done).length, 0), [week])
  const totalCount = useMemo(() => week.reduce((sum, day) => sum + day.tasks.length, 0), [week])

  const toggleTask = (dayIndex: number, taskId: number) => setWeek((current) => current.map((day, index) => index === dayIndex ? { ...day, tasks: day.tasks.map((task) => task.id === taskId ? { ...task, done: !task.done } : task) } : day))
  const toggleGoal = (index: number) => setGoals((current) => current.map((goal, goalIndex) => goalIndex === index ? { ...goal, done: !goal.done } : goal))

  return (
    <div className="data-page schedule-page">
      <div className="schedule-grid">
        <section className="schedule-main">
          <header className="page-title-block"><h1>Расписание по дням</h1><p>Планируйте неделю, фиксируйте результаты и анализируйте прогресс</p></header>
          <div className="schedule-controls"><div className="week-switcher"><button type="button" aria-label="Предыдущая неделя"><ChevronLeft /></button><strong>Неделя 20–26 июля 2026</strong><button type="button" aria-label="Следующая неделя"><ChevronRight /></button><button className="today-button" type="button"><CalendarDays size={16} />Сегодня</button></div><button className="solid-action" type="button" onClick={() => setShowModal(true)}><Plus size={19} />Добавить задачу</button></div>
          <div className="metrics-grid schedule-metrics"><MetricCard icon={ListChecks} label="Задач на неделю" value="42" hint="+6 к прошлой неделе" accent="blue" /><MetricCard icon={CheckCircle2} label="Выполнено" value="26" hint="62% от плана" accent="green" /><MetricCard icon={CalendarDays} label="Важные встречи" value="7" hint="3 на этой неделе" accent="purple" /><MetricCard icon={Target} label="Фокус недели" value="" hint="Фокус на проектах и поиске работы" accent="orange" /></div>

          <div className="week-board">{week.map((day, dayIndex) => <WeekColumn day={day} dayIndex={dayIndex} onToggle={toggleTask} key={day.date} />)}</div>

          <div className="schedule-bottom-grid">
            <section className="summary-panel"><div className="summary-panel-title"><div><h2>Итоги недели</h2><p>Подведите итоги недели: успехи, проблемы, идеи и выводы</p></div><span>{summary.length} / 2000</span></div><textarea value={summary} onChange={(event) => setSummary(event.target.value)} aria-label="Итоги недели" /><button className="solid-action save-summary" type="button"><Check size={18} />Сохранить итоги недели</button></section>
            <section className="goals-panel"><div className="summary-panel-title"><h2>Цели на неделю</h2><button type="button">Изменить</button></div><div className="goal-list">{goals.map((goal, index) => <button type="button" className="goal-row" key={goal.title} onClick={() => toggleGoal(index)}><span className={`goal-check ${goal.done ? 'done' : ''}`}>{goal.done && <Check size={12} />}</span><span>{goal.title}</span>{goal.progress && <><ProgressMini /><small>{goal.progress}</small></>}<span className="drag-handle">⁝⁝</span></button>)}</div></section>
          </div>
        </section>

        <aside className="schedule-side-column">
          <SidePanel className="calendar-panel"><div className="calendar-title-row"><h2>Календарь</h2></div><div className="month-switcher"><button type="button" aria-label="Предыдущий месяц"><ChevronLeft /></button><strong>Июль 2026 <ChevronDownSmall /></strong><button type="button" aria-label="Следующий месяц"><ChevronRight /></button></div><CalendarGrid selectedDate={selectedDate} onSelect={setSelectedDate} /></SidePanel>
          <SidePanel className="upcoming-panel"><div className="side-panel-title-row"><h2>Ближайшие события</h2><button type="button">Смотреть все</button></div><div className="upcoming-list">{upcoming.map(([date, time, title, meta, tone]) => <div key={title}><p><strong>{date}</strong><b>{time}</b></p><span className={tone} /><div><strong>{title}</strong><small>{meta}</small></div></div>)}</div></SidePanel>
          <SidePanel className="past-panel"><h2>Прошлые недели</h2>{['13–19 июля 2026', '6–12 июля 2026', '29 июня – 5 июля 2026'].map((label) => <button type="button" key={label}>{label}<ChevronRight size={15} /></button>)}<button className="archive-button" type="button">Открыть архив</button></SidePanel>
          <SidePanel className="quick-actions-panel"><h2>Быстрые действия</h2><div><button type="button" onClick={() => setShowModal(true)}><CheckCircle2 />Добавить задачу</button><button type="button"><FileText />Добавить заметку дня</button></div></SidePanel>
        </aside>
      </div>
      {showModal && <TaskModal onClose={() => setShowModal(false)} />}
    </div>
  )
}

function WeekColumn({ day, dayIndex, onToggle }: { day: WeekDay; dayIndex: number; onToggle: (dayIndex: number, taskId: number) => void }) {
  return <article className="week-column"><header><strong>{day.short}</strong><span>{day.date}</span><b>{day.count}</b></header><div className="day-task-list">{day.tasks.map((task) => <button type="button" className={`day-task ${task.done ? 'done' : ''}`} key={task.id} onClick={() => onToggle(dayIndex, task.id)}><span className="task-check">{task.done && <Check size={12} />}</span><span><strong>{task.title}</strong>{task.time && <small>{task.time}</small>}</span></button>)}</div><div className="day-note"><small>Что произошло</small><p>{day.note}</p><button type="button"><Plus size={13} />Заметка дня</button></div></article>
}

function CalendarGrid({ selectedDate, onSelect }: { selectedDate: number; onSelect: (date: number) => void }) {
  const cells = [29, 30, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 1, 2]
  return <div className="mini-calendar"><div className="calendar-weekdays">{['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((item) => <span key={item}>{item}</span>)}</div><div className="calendar-cells">{cells.map((date, index) => <button type="button" key={`${date}-${index}`} className={`${index < 2 || index > 33 ? 'muted' : ''} ${date === selectedDate && index > 20 && index < 28 ? 'selected-day' : ''}`} onClick={() => onSelect(date)}>{date}</button>)}</div><div className="calendar-range"><span className="range-selected">20</span>{[21, 22, 23, 24, 25, 26].map((date) => <button type="button" key={date} onClick={() => onSelect(date)}>{date}</button>)}</div></div>
}

function ProgressMini() { return <span className="goal-progress"><i /></span> }
function ChevronDownSmall() { return <ChevronRight className="chevron-down" size={14} /> }

function TaskModal({ onClose }: { onClose: () => void }) {
  const [title, setTitle] = useState('')
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="compact-modal" onSubmit={(event) => { event.preventDefault(); onClose() }} onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><span className="metric-icon blue"><CheckCircle2 /></span><h2>Новая задача</h2><label htmlFor="task-title">Название задачи</label><input id="task-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, Подготовить отчёт" /><button className="solid-action wide-action" type="submit" disabled={!title.trim()}><Plus size={18} />Добавить задачу</button></form></div>
}
