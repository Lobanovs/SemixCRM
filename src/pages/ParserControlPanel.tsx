import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  Hash,
  Infinity as InfinityIcon,
  ListOrdered,
  MapPin,
  Minus,
  PawPrint,
  Play,
  Save,
  Search,
  Sparkles,
  X,
} from 'lucide-react'

import type { ParserSettings } from './parserSettings'
import { parserSettingsEqual } from './parserSettings'

type ParserFeedback = { kind: 'status' | 'error'; text: string } | null

type ParserControlPanelProps = {
  settings: ParserSettings
  savedSettings: ParserSettings
  cities: string[]
  availableNiches: string[]
  foundToday: number
  newToday: number
  isSaving: boolean
  isParsing: boolean
  isReady: boolean
  feedback: ParserFeedback
  onChange: (settings: ParserSettings) => void
  onSave: () => void
  onRun: () => void
}

const sourceName = (source: string) => source === '2gis' ? '2GIS' : source === 'yandex' ? 'Яндекс Карты' : source

export default function ParserControlPanel({
  settings,
  savedSettings,
  cities,
  availableNiches,
  foundToday,
  newToday,
  isSaving,
  isParsing,
  isReady,
  feedback,
  onChange,
  onSave,
  onRun,
}: ParserControlPanelProps) {
  const [showNiches, setShowNiches] = useState(false)
  const [startPageInput, setStartPageInput] = useState(String(settings.start_page))
  const [limitInput, setLimitInput] = useState(String(settings.limit > 0 ? settings.limit : 50))
  const nicheTriggerRef = useRef<HTMLButtonElement>(null)
  const lastFiniteLimitRef = useRef(settings.limit > 0 ? settings.limit : 50)
  const dirty = !parserSettingsEqual(settings, savedSettings)
  const locked = !isReady || isSaving || isParsing
  const selectedNiches = settings.niches.slice(0, 2)
  const extraNiches = Math.max(0, settings.niches.length - selectedNiches.length)
  const validationMessage = !settings.niches.length
    ? 'Выберите хотя бы одну нишу'
    : !settings.sources.length
      ? 'Выберите хотя бы один источник'
      : ''

  useEffect(() => setStartPageInput(String(settings.start_page)), [settings.start_page])
  useEffect(() => {
    if (settings.limit <= 0) return
    lastFiniteLimitRef.current = settings.limit
    setLimitInput(String(settings.limit))
  }, [settings.limit])

  const update = <Key extends keyof ParserSettings>(key: Key, value: ParserSettings[Key]) => {
    onChange({ ...settings, [key]: value })
  }

  const toggleSource = (source: string) => {
    const sources = settings.sources.includes(source)
      ? settings.sources.filter((item) => item !== source)
      : [...settings.sources, source]
    const limit = !sources.includes('2gis') && settings.limit === 0
      ? lastFiniteLimitRef.current
      : settings.limit
    onChange({ ...settings, sources, limit })
  }

  const useUnlimitedScope = () => update('limit', 0)

  const useFiniteScope = () => {
    const limit = Math.max(1, lastFiniteLimitRef.current)
    setLimitInput(String(limit))
    update('limit', limit)
  }

  const updateFiniteLimit = (value: string) => {
    setLimitInput(value)
    if (!/^\d+$/.test(value)) return
    const limit = Math.max(1, Math.round(Number(value)))
    if (!Number.isFinite(limit)) return
    lastFiniteLimitRef.current = limit
    update('limit', limit)
  }

  const commitFiniteLimit = () => {
    const parsed = Number(limitInput)
    const limit = Number.isFinite(parsed) ? Math.max(1, Math.round(parsed)) : lastFiniteLimitRef.current
    lastFiniteLimitRef.current = limit
    setLimitInput(String(limit))
    if (settings.limit !== limit) update('limit', limit)
  }

  const closeNiches = () => {
    setShowNiches(false)
    window.setTimeout(() => nicheTriggerRef.current?.focus(), 0)
  }

  const statusText = !isReady
    ? 'Загружаю сохранённые настройки'
    : isParsing
    ? 'Парсер работает'
    : isSaving
      ? 'Сохраняю настройки'
      : dirty
        ? 'Есть несохранённые изменения'
        : 'Настройки сохранены'

  return <>
    <div className="parser-control-heading" data-guide="clients-parser">
      <span className="parser-control-icon"><PawPrint size={22} /></span>
      <div>
        <h2>Парсер клиентов</h2>
        <p>Настройте поиск и запустите сбор компаний из публичных карточек.</p>
      </div>
    </div>

    <div className={`parser-control-state ${isReady && dirty ? 'dirty' : ''} ${isParsing ? 'running' : ''} ${!isReady ? 'loading' : ''}`}>
      <span aria-hidden="true" />
      {statusText}
    </div>

    <div className="parser-control-stats" aria-label="Статистика парсера за сегодня">
      <span>Найдено сегодня<strong>{foundToday}</strong></span>
      <span>Новых<strong>{newToday}</strong></span>
    </div>

    <fieldset className="parser-control-section" disabled={locked}>
      <legend>Параметры поиска</legend>

      <label className="parser-control-field" htmlFor="parser-control-city">
        <span><MapPin size={15} />Город</span>
        <select id="parser-control-city" value={settings.city} onChange={(event) => update('city', event.target.value)}>
          {cities.map((city) => <option key={city}>{city}</option>)}
        </select>
      </label>

      <div className="parser-control-field">
        <span><Search size={15} />Ниши <b>{settings.niches.length}</b></span>
        <div className="parser-control-niches">
          <p>{selectedNiches.length ? <>{selectedNiches.join(', ')}{extraNiches > 0 && <strong> +{extraNiches}</strong>}</> : 'Ниши не выбраны'}</p>
          <button ref={nicheTriggerRef} type="button" onClick={() => setShowNiches(true)}>Выбрать</button>
        </div>
      </div>

      <div className="parser-control-field">
        <span><Sparkles size={15} />Источники</span>
        <div className="parser-control-sources">
          {['2gis', 'yandex'].map((source) => {
            const active = settings.sources.includes(source)
            return <button
              type="button"
              className={active ? 'active' : ''}
              aria-pressed={active}
              onClick={() => toggleSource(source)}
              key={source}
            >
              <MapPin size={16} />{sourceName(source)}{active && <Check size={15} />}
            </button>
          })}
        </div>
      </div>

      <div className={`parser-control-page ${settings.sources.includes('2gis') ? '' : 'disabled'}`}>
        <div>
          <label htmlFor="parser-control-start-page"><ListOrdered size={15} />Стартовая страница 2GIS</label>
          <p>Парсер пропустит предыдущие страницы и начнёт с указанной.</p>
        </div>
        <div className="parser-control-stepper">
          <button type="button" aria-label="Уменьшить стартовую страницу" disabled={!settings.sources.includes('2gis') || settings.start_page <= 1} onClick={() => update('start_page', Math.max(1, settings.start_page - 1))}><Minus size={17} /></button>
          <input
            id="parser-control-start-page"
            type="number"
            min="1"
            max="999"
            step="1"
            value={startPageInput}
            disabled={!settings.sources.includes('2gis')}
            onChange={(event) => {
              const value = event.target.value
              setStartPageInput(value)
              if (value !== '') update('start_page', Math.max(1, Math.min(999, Number(value) || 1)))
            }}
            onBlur={() => setStartPageInput(String(settings.start_page))}
          />
          <button type="button" aria-label="Увеличить стартовую страницу" disabled={!settings.sources.includes('2gis') || settings.start_page >= 999} onClick={() => update('start_page', Math.min(999, settings.start_page + 1))}>+</button>
        </div>
      </div>

      <div className="parser-control-scope">
        <div className="parser-control-scope-heading">
          <span><Hash size={15} />Объём парсинга</span>
          <strong>{settings.limit === 0 ? 'Без лимита' : `${settings.limit} компаний`}</strong>
        </div>
        <div className="parser-control-scope-options" role="group" aria-label="Объём парсинга">
          <button
            type="button"
            aria-label="Все компании"
            aria-pressed={settings.limit === 0}
            className={settings.limit === 0 ? 'active' : ''}
            disabled={!settings.sources.includes('2gis')}
            onClick={useUnlimitedScope}
          >
            <InfinityIcon size={18} />
            <span><strong>Все компании</strong><small>До конца выдачи 2GIS</small></span>
            {settings.limit === 0 && <Check size={15} />}
          </button>
          <button
            type="button"
            aria-label="Указать лимит"
            aria-pressed={settings.limit > 0}
            className={settings.limit > 0 ? 'active' : ''}
            onClick={useFiniteScope}
          >
            <Hash size={17} />
            <span>
              <strong>Указать лимит</strong>
              <small>{settings.sources.includes('2gis') ? 'Любое количество для 2GIS' : 'До 50 в Яндекс Картах'}</small>
            </span>
            {settings.limit > 0 && <Check size={15} />}
          </button>
        </div>
        {settings.limit > 0 && <label className="parser-control-limit-input" htmlFor="parser-control-limit">
          <span>Компаний на нишу и источник</span>
          <input
            id="parser-control-limit"
            type="number"
            min="1"
            step="1"
            inputMode="numeric"
            value={limitInput}
            onChange={(event) => updateFiniteLimit(event.target.value)}
            onBlur={commitFiniteLimit}
          />
        </label>}
        <p className="parser-control-scope-hint">
          {settings.limit === 0
            ? settings.sources.includes('yandex')
              ? '2GIS будет собран до последней страницы. Яндекс Карты — до 50 компаний на нишу.'
              : 'Парсер пройдёт 2GIS от стартовой до последней страницы и соберёт всю доступную выдачу.'
            : settings.sources.includes('yandex')
              ? settings.sources.includes('2gis')
                ? `2GIS остановится после ${settings.limit} компаний. Яндекс Карты — до ${Math.min(settings.limit, 50)} компаний на нишу.`
                : `Яндекс Карты соберут до ${Math.min(settings.limit, 50)} компаний на нишу.`
              : `2GIS остановится после ${settings.limit} компаний для каждой выбранной ниши.`}
        </p>
      </div>
    </fieldset>

    {isReady && validationMessage && <p className="parser-control-validation" role="alert">{validationMessage}. Верните источник или нишу, чтобы сохранить настройки и запустить парсер.</p>}
    {feedback && <p className={`parser-control-feedback ${feedback.kind}`} role={feedback.kind === 'error' ? 'alert' : 'status'}>{feedback.text}</p>}

    <div className="parser-control-actions">
      <button className="parser-save-action" type="button" onClick={onSave} disabled={locked || !dirty || Boolean(validationMessage)}>
        {isSaving ? <Sparkles className="spin" size={17} /> : <Save size={17} />}
        {isSaving ? 'Сохраняю…' : 'Сохранить настройки'}
      </button>
      <button className="parser-run-action" type="button" data-guide="clients-run" onClick={onRun} disabled={locked || Boolean(validationMessage)}>
        {isParsing ? <Sparkles className="spin" size={17} /> : <Play size={17} />}
        {isParsing ? 'Парсер работает…' : 'Запустить парсер'}
      </button>
    </div>

    {showNiches && <ParserNichesDialog
      niches={settings.niches}
      availableNiches={availableNiches}
      onClose={closeNiches}
      onApply={(niches) => { update('niches', niches); closeNiches() }}
    />}
  </>
}

function ParserNichesDialog({ niches, availableNiches, onClose, onApply }: {
  niches: string[]
  availableNiches: string[]
  onClose: () => void
  onApply: (niches: string[]) => void
}) {
  const [selected, setSelected] = useState(niches)
  const [query, setQuery] = useState('')
  const dialogRef = useRef<HTMLElement>(null)
  const visibleNiches = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('ru')
    return availableNiches.filter((item) => !normalized || item.toLocaleLowerCase('ru').includes(normalized))
  }, [availableNiches, query])

  useEffect(() => {
    const handleDialogKeys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), [href]') ?? [])
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handleDialogKeys)
    return () => window.removeEventListener('keydown', handleDialogKeys)
  }, [onClose])

  const toggle = (niche: string) => {
    setSelected((items) => items.includes(niche) ? items.filter((item) => item !== niche) : [...items, niche])
  }

  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
    <section ref={dialogRef} className="parser-niches-dialog" role="dialog" aria-modal="true" aria-labelledby="parser-niches-title" onMouseDown={(event) => event.stopPropagation()}>
      <header>
        <div><h2 id="parser-niches-title">Выберите ниши</h2><p>Можно отметить несколько направлений. Изменения применятся после сохранения панели.</p></div>
        <button type="button" onClick={onClose} aria-label="Закрыть выбор ниш"><X size={20} /></button>
      </header>
      <div className="parser-niches-body">
        <label className="parser-niches-search"><span className="sr-only">Поиск ниши</span><Search size={17} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти нишу" /></label>
        <div className="parser-niches-summary"><strong>{selected.length}</strong> выбрано</div>
        <div className="parser-niches-grid">
          {visibleNiches.map((niche) => <label className={selected.includes(niche) ? 'active' : ''} key={niche}>
            <input type="checkbox" checked={selected.includes(niche)} onChange={() => toggle(niche)} />
            <span className="parser-checkbox-mark">{selected.includes(niche) && <Check size={14} />}</span>
            <span>{niche}</span>
          </label>)}
          {!visibleNiches.length && <p className="parser-niches-empty">По вашему запросу ничего не найдено.</p>}
        </div>
      </div>
      <footer>
        {!selected.length && <p role="alert">Выберите хотя бы одну нишу</p>}
        <div><button type="button" onClick={onClose}>Отмена</button><button type="button" disabled={!selected.length} onClick={() => onApply(selected)}>Применить</button></div>
      </footer>
    </section>
  </div>
}
