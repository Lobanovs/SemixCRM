import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  BriefcaseBusiness,
  CalendarCheck2,
  CircleCheck,
  LoaderCircle,
  MessageSquareText,
  RefreshCw,
  SearchCheck,
  Sparkles,
  UsersRound,
} from 'lucide-react'

import { apiRequest } from '../api'
import type { LucideIcon } from 'lucide-react'


export type ActionSection = 'clients' | 'schedule' | 'jobs' | 'freelance'

type DashboardStats = {
  clients_total: number
  clients_to_contact: number
  tasks_open: number
  jobs_new: number
  freelance_active: number
}

type ClientAction = { id: number; name: string; niche: string; city: string; score: number; score_max: number; rating: number | null; reviews: number; phone: string }
type TaskAction = { id: number; title: string; date: string; time: string; kind: string }
type JobAction = { id: number; role: string; company: string; source: string; relevance: number; salary_text: string; discovered_at: string }
type FreelanceAction = { id: number; title: string; source: string; relevance: number; budget_text: string; published_at: string }
type SourceHealth = { kind: string; source: string; status: string; state: string; checked_at: string; error: string; is_stale: boolean; needs_attention: boolean }

export type DashboardPayload = {
  generated_at?: string
  stats: DashboardStats
  clients: ClientAction[]
  tasks: TaskAction[]
  jobs: JobAction[]
  freelance: FreelanceAction[]
  source_health: SourceHealth[]
}

const sourceLabels: Record<string, string> = {
  kwork: 'Kwork', fl: 'FL.ru', freelance_ru: 'Freelance.ru', profi: 'Profi.ru', youdo: 'YouDo',
  hh: 'hh.ru', habr: 'Хабр Карьера', telegram: 'Telegram', remoteok: 'RemoteOK',
  remotive: 'Remotive', weworkremotely: 'We Work Remotely',
}

const formatDate = (date: string, time = '') => {
  if (!date) return time || 'Без срока'
  const value = new Date(`${date}T${time || '00:00'}:00`)
  if (Number.isNaN(value.getTime())) return [date, time].filter(Boolean).join(' · ')
  return value.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' }) + (time ? ` · ${time}` : '')
}

export default function ActionCenter({ onOpen }: { onOpen: (section: ActionSection) => void }) {
  const [data, setData] = useState<DashboardPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await apiRequest<DashboardPayload>('/api/dashboard?limit=5', { fallback: 'Не удалось загрузить центр действий' }))
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Не удалось загрузить центр действий')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  if (loading && !data) {
    return (
      <section className="action-center action-center-loading" aria-label="Загрузка центра действий">
        <LoaderCircle className="spin" size={24} />
        <div><strong>Собираю дела на сегодня</strong><span>Клиенты, задачи и новые возможности</span></div>
      </section>
    )
  }

  if (error && !data) {
    return (
      <section className="action-center action-center-error" aria-live="polite">
        <AlertTriangle size={25} />
        <div><strong>Центр действий временно недоступен</strong><span>{error}</span></div>
        <button type="button" onClick={() => void load()}><RefreshCw size={17} />Повторить загрузку</button>
      </section>
    )
  }

  if (!data) return null
  const attention = data.source_health.filter((item) => item.needs_attention)

  return (
    <section className="action-center" aria-labelledby="action-center-title">
      <header className="action-center-header">
        <div>
          <span className="action-center-kicker"><Sparkles size={15} />Рабочий центр</span>
          <h2 id="action-center-title">Что важно сегодня</h2>
          <p>Начните с приоритетных действий — CRM уже собрала их в одном месте.</p>
        </div>
        <button className="action-refresh" type="button" onClick={() => void load()} disabled={loading} aria-label="Обновить центр действий">
          <RefreshCw className={loading ? 'spin' : ''} size={18} />Обновить
        </button>
      </header>

      <div className="action-metrics" aria-label="Краткая статистика" data-guide="home-stats">
        <ActionMetric icon={UsersRound} value={data.stats.clients_to_contact} label="ждут первого сообщения" tone="blue" />
        <ActionMetric icon={CalendarCheck2} value={data.stats.tasks_open} label="открытых задач" tone="orange" />
        <ActionMetric icon={BriefcaseBusiness} value={data.stats.jobs_new} label="вакансий для отклика" tone="green" />
        <ActionMetric icon={SearchCheck} value={data.stats.freelance_active} label="активных заказов" tone="purple" />
      </div>

      <div className="action-queues">
        <ActionQueue title="Клиенты для контакта" count={data.stats.clients_to_contact} icon={MessageSquareText} tone="blue" section="clients" onOpen={onOpen} empty="Новых клиентов для контакта нет.">
          {data.clients.map((item) => (
            <ActionItem key={item.id} title={item.name} meta={[item.niche, item.city].filter(Boolean).join(' · ')} badge={`${item.score}/${item.score_max}`} />
          ))}
        </ActionQueue>

        <ActionQueue title="План на неделю" count={data.stats.tasks_open} icon={CalendarCheck2} tone="orange" section="schedule" onOpen={onOpen} empty="На этой неделе открытых задач нет.">
          {data.tasks.map((item) => <ActionItem key={item.id} title={item.title} meta={formatDate(item.date, item.time)} badge={item.time || 'Задача'} />)}
        </ActionQueue>

        <ActionQueue title="Вакансии для отклика" count={data.stats.jobs_new} icon={BriefcaseBusiness} tone="green" section="jobs" onOpen={onOpen} empty="Новых вакансий для отклика нет.">
          {data.jobs.map((item) => <ActionItem key={item.id} title={item.role} meta={`${item.company} · ${sourceLabels[item.source] ?? item.source}`} badge={`${item.relevance}%`} />)}
        </ActionQueue>

        <ActionQueue title="Фриланс-заказы" count={data.stats.freelance_active} icon={SearchCheck} tone="purple" section="freelance" onOpen={onOpen} empty="Активных фриланс-заказов нет.">
          {data.freelance.map((item) => <ActionItem key={item.id} title={item.title} meta={`${sourceLabels[item.source] ?? item.source}${item.budget_text ? ` · ${item.budget_text}` : ''}`} badge={`${item.relevance}%`} />)}
        </ActionQueue>
      </div>

      <div className={`source-health-strip ${attention.length ? 'has-attention' : ''}`}>
        {attention.length ? <AlertTriangle size={18} /> : <CircleCheck size={18} />}
        <div>
          <strong>{attention.length ? `${attention.length} источников требуют внимания` : 'Источники работают штатно'}</strong>
          <span>{attention.length
            ? attention.slice(0, 4).map((item) => `${sourceLabels[item.source] ?? item.source} требует внимания`).join(' · ')
            : 'Последние проверки не обнаружили проблем'}</span>
        </div>
        {attention.length > 0 && <button type="button" onClick={() => onOpen(attention.some((item) => item.kind === 'freelance') ? 'freelance' : 'jobs')}>Проверить <ArrowRight size={15} /></button>}
      </div>
      {error && <p className="action-refresh-error" role="status">Данные показаны из последней загрузки: {error}</p>}
    </section>
  )
}

function ActionMetric({ icon: Icon, value, label, tone }: { icon: LucideIcon; value: number; label: string; tone: string }) {
  return <article className={`action-metric ${tone}`}><Icon size={20} /><strong>{value.toLocaleString('ru-RU')}</strong><span>{label}</span></article>
}

function ActionQueue({ title, count, icon: Icon, tone, section, onOpen, empty, children }: {
  title: string; count: number; icon: LucideIcon; tone: string; section: ActionSection; onOpen: (section: ActionSection) => void; empty: string; children: ReactNode
}) {
  const hasItems = Array.isArray(children) ? children.length > 0 : Boolean(children)
  return (
    <article className={`action-queue ${tone}`}>
      <header><span className="action-queue-icon"><Icon size={19} /></span><div><h3>{title}</h3><span>{count.toLocaleString('ru-RU')} всего</span></div><button type="button" onClick={() => onOpen(section)} aria-label={`Открыть ${section === 'clients' ? 'клиентов' : section === 'schedule' ? 'расписание' : section === 'jobs' ? 'вакансии' : 'фриланс'}`}><ArrowRight size={17} /></button></header>
      <div className="action-queue-list">{hasItems ? children : <p className="action-queue-empty">{empty}</p>}</div>
    </article>
  )
}

function ActionItem({ title, meta, badge }: { title: string; meta: string; badge: string }) {
  return <div className="action-item"><div><strong>{title}</strong><span>{meta}</span></div><b>{badge}</b></div>
}
