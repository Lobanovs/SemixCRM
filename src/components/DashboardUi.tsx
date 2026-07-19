import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

export type UiAccent = 'blue' | 'green' | 'orange' | 'purple' | 'pink' | 'red' | 'cyan' | 'gray'

export function MetricCard({
  icon: Icon,
  label,
  value,
  hint,
  accent = 'blue',
}: {
  icon: LucideIcon
  label: string
  value: string | number
  hint: string
  accent?: UiAccent
}) {
  return (
    <article className="metric-card">
      <span className={`metric-icon ${accent}`}><Icon size={29} strokeWidth={1.8} /></span>
      <div className="metric-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{hint}</small>
      </div>
    </article>
  )
}

export function StatusBadge({ children, tone = 'blue' }: { children: ReactNode; tone?: UiAccent }) {
  return <span className={`status-badge ${tone}`}>{children}</span>
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="data-tag">{children}</span>
}

export function SidePanel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`side-panel ${className}`}>{children}</section>
}

export function ProgressBar({ value, tone = 'blue' }: { value: number; tone?: UiAccent }) {
  return (
    <span className="progress-track" aria-label={`Готовность ${value}%`}>
      <span className={`progress-value ${tone}`} style={{ width: `${Math.max(0, Math.min(value, 100))}%` }} />
    </span>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="page-empty-state">{children}</div>
}
