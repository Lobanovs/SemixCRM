import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, GraduationCap, Lightbulb, MousePointerClick, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { UiAccent } from './DashboardUi'

export type GuideStep = {
  /** Заголовок шага — что пользователь делает. */
  title: string
  /** Что произойдёт и на что смотреть. */
  body: string
  icon: LucideIcon
  accent?: UiAccent
  /** Подпись реальной кнопки в интерфейсе, если шаг про неё. */
  control?: string
  /** CSS-селектор элемента, который тур подсветит на экране. */
  selector?: string
  /** Короткая приписка мелким шрифтом: нюанс, о котором легко забыть. */
  hint?: string
}

type PageGuideProps = {
  /** Ключ раздела: по нему запоминается, что инструкцию уже открывали. */
  sectionId: string
  title: string
  intro: string
  steps: GuideStep[]
}

const SEEN_PREFIX = 'semix-crm-guide-seen:'
const TOOLTIP_WIDTH = 340
const GAP = 14

function markSeen(sectionId: string) {
  try {
    window.localStorage.setItem(`${SEEN_PREFIX}${sectionId}`, '1')
  } catch {
    // приватный режим браузера — не повод ломать страницу
  }
}

function wasSeen(sectionId: string) {
  try {
    return window.localStorage.getItem(`${SEEN_PREFIX}${sectionId}`) === '1'
  } catch {
    return true
  }
}

export default function PageGuide({ sectionId, title, intro, steps }: PageGuideProps) {
  // Первый заход в раздел открывает инструкцию сам, дальше — только по кнопке.
  const [open, setOpen] = useState(() => !wasSeen(sectionId))
  const [tourAt, setTourAt] = useState<number | null>(null)

  useEffect(() => {
    if (open) markSeen(sectionId)
  }, [open, sectionId])

  const tourSteps = useMemo(() => steps.filter((step) => step.selector), [steps])

  const startTour = () => {
    const first = tourSteps.findIndex((step) => document.querySelector(step.selector as string))
    setTourAt(first === -1 ? null : first)
    if (first === -1) window.alert('Элементы этого раздела появятся, когда в нём будут данные. Инструкция ниже описывает все шаги.')
  }

  return (
    <section className={`page-guide ${open ? 'is-open' : ''}`}>
      <header className="page-guide-head">
        <span className="page-guide-icon"><GraduationCap size={22} /></span>
        <div>
          <h2>{title}</h2>
          <p>{intro}</p>
        </div>
        <div className="page-guide-head-actions">
          {open && tourSteps.length > 0 && (
            <button className="guide-tour-start" type="button" onClick={startTour}>
              <MousePointerClick size={16} />Показать на экране
            </button>
          )}
          <button className="guide-toggle" type="button" onClick={() => setOpen((current) => !current)} aria-expanded={open}>
            {open ? 'Свернуть' : 'Как пользоваться'}
          </button>
        </div>
      </header>

      {open && (
        <ol className="page-guide-steps">
          {steps.map((step, index) => {
            const Icon = step.icon
            return (
              <li key={step.title}>
                <span className={`guide-step-icon ${step.accent ?? 'blue'}`}><Icon size={19} /></span>
                <div>
                  <h3><b>{index + 1}</b>{step.title}</h3>
                  <p>{step.body}</p>
                  {step.control && <span className="guide-control-chip">{step.control}</span>}
                  {step.hint && <small><Lightbulb size={13} />{step.hint}</small>}
                </div>
              </li>
            )
          })}
        </ol>
      )}

      {tourAt !== null && (
        <GuideTour
          steps={tourSteps}
          index={tourAt}
          onIndex={setTourAt}
          onClose={() => setTourAt(null)}
        />
      )}
    </section>
  )
}

type Rect = { top: number; left: number; width: number; height: number }

function GuideTour({
  steps, index, onIndex, onClose,
}: {
  steps: GuideStep[]
  index: number
  onIndex: (value: number) => void
  onClose: () => void
}) {
  const [rect, setRect] = useState<Rect | null>(null)
  const [tooltipHeight, setTooltipHeight] = useState(180)
  const tooltipRef = useRef<HTMLDivElement | null>(null)
  const step = steps[index]

  const measure = useCallback(() => {
    const target = step?.selector ? document.querySelector(step.selector) : null
    if (!target) { setRect(null); return }
    const box = target.getBoundingClientRect()
    setRect({ top: box.top, left: box.left, width: box.width, height: box.height })
  }, [step])

  useEffect(() => {
    const target = step?.selector ? document.querySelector(step.selector) : null
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    // Даём прокрутке долететь до места, иначе подсветка встанет по старым координатам.
    const timer = window.setTimeout(measure, 320)
    return () => window.clearTimeout(timer)
  }, [step, measure])

  useEffect(() => {
    measure()
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [measure])

  useLayoutEffect(() => {
    if (tooltipRef.current) setTooltipHeight(tooltipRef.current.offsetHeight)
  }, [index, rect])

  // Следующий и предыдущий шаги, у которых элемент реально есть на странице.
  const findNeighbour = useCallback((direction: 1 | -1) => {
    for (let cursor = index + direction; cursor >= 0 && cursor < steps.length; cursor += direction) {
      if (document.querySelector(steps[cursor].selector as string)) return cursor
    }
    return -1
  }, [index, steps])

  const next = findNeighbour(1)
  const previous = findNeighbour(-1)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowRight' && next !== -1) onIndex(next)
      if (event.key === 'ArrowLeft' && previous !== -1) onIndex(previous)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, previous, onIndex, onClose])

  if (!step) return null

  const belowFits = rect ? rect.top + rect.height + GAP + tooltipHeight < window.innerHeight : true
  const tooltipTop = rect
    ? (belowFits ? rect.top + rect.height + GAP : Math.max(GAP, rect.top - tooltipHeight - GAP))
    : Math.max(GAP, window.innerHeight / 2 - tooltipHeight / 2)
  const tooltipLeft = rect
    ? Math.min(Math.max(GAP, rect.left + rect.width / 2 - TOOLTIP_WIDTH / 2), window.innerWidth - TOOLTIP_WIDTH - GAP)
    : window.innerWidth / 2 - TOOLTIP_WIDTH / 2

  const Icon = step.icon

  return (
    <div
      className="guide-tour-layer"
      role="dialog"
      aria-modal="true"
      aria-label={`Подсказка: ${step.title}`}
      data-active-selector={step.selector}
    >
      <button className="guide-tour-backdrop" type="button" aria-label="Закрыть подсказку" onClick={onClose} />
      {rect && (
        <span
          className="guide-tour-spot"
          style={{ top: rect.top - 6, left: rect.left - 6, width: rect.width + 12, height: rect.height + 12 }}
        />
      )}
      <div className="guide-tour-tip" ref={tooltipRef} style={{ top: tooltipTop, left: tooltipLeft, width: TOOLTIP_WIDTH }}>
        <button className="guide-tour-close" type="button" onClick={onClose} aria-label="Закрыть подсказку"><X size={17} /></button>
        <span className={`guide-step-icon ${step.accent ?? 'blue'}`}><Icon size={18} /></span>
        <h3>{step.title}</h3>
        <p>{step.body}</p>
        {step.hint && <small>{step.hint}</small>}
        <footer>
          <span>{index + 1} из {steps.length}</span>
          <div>
            <button type="button" onClick={() => onIndex(previous)} disabled={previous === -1}>
              <ChevronLeft size={15} />Назад
            </button>
            {next === -1 ? (
              <button className="guide-tour-finish" type="button" onClick={onClose}>Готово</button>
            ) : (
              <button className="guide-tour-finish" type="button" onClick={() => onIndex(next)}>
                Далее<ChevronRight size={15} />
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  )
}
