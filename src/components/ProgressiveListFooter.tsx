import { ChevronsDown, ListPlus } from 'lucide-react'


const formatCount = (value: number) => value.toLocaleString('ru-RU').replace(/\u00a0/g, ' ')

export default function ProgressiveListFooter({ shown, total, step, onMore, onAll }: {
  shown: number
  total: number
  step: number
  onMore: () => void
  onAll: () => void
}) {
  const visible = Math.min(Math.max(0, shown), Math.max(0, total))
  if (visible >= total || total <= 0) return null
  const next = Math.min(Math.max(1, step), total - visible)

  return (
    <div className="progressive-list-footer" aria-label="Управление длинным списком">
      <span>{`Показано ${formatCount(visible)} из ${formatCount(total)}`}</span>
      <div>
        <button type="button" onClick={onMore} aria-label={`Показать ещё ${formatCount(next)}`}><ListPlus size={16} />Показать ещё {formatCount(next)}</button>
        <button type="button" onClick={onAll} aria-label={`Показать все ${formatCount(total)}`}><ChevronsDown size={16} />Показать все</button>
      </div>
    </div>
  )
}
