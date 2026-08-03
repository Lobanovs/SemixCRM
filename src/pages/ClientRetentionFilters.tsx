import { Check, RotateCcw, SlidersHorizontal, X } from 'lucide-react'

import {
  countActiveClientFilters,
  describeClientFilters,
} from './clientFilters'
import type {
  ClientAiMessageFilter,
  ClientRetentionFilterState,
  ClientWebsiteFilter,
  RequiredClientContact,
} from './clientFilters'

type ClientRetentionFiltersProps = {
  filters: ClientRetentionFilterState
  isOpen: boolean
  totalCount: number
  visibleCount: number
  onChange: (filters: ClientRetentionFilterState) => void
  onClose: () => void
  onReset: () => void
}

const scorePresets = [0, 10, 15, 18]
const contactOptions: Array<{ value: RequiredClientContact; label: string; hint: string }> = [
  { value: 'telegram', label: 'Telegram', hint: 'Можно написать напрямую' },
  { value: 'whatsapp', label: 'WhatsApp', hint: 'Есть быстрый чат' },
  { value: 'phone', label: 'Телефон', hint: 'Можно позвонить' },
  { value: 'email', label: 'E-mail', hint: 'Можно отправить письмо' },
]

export default function ClientRetentionFilters({
  filters,
  isOpen,
  totalCount,
  visibleCount,
  onChange,
  onClose,
  onReset,
}: ClientRetentionFiltersProps) {
  const activeCount = countActiveClientFilters(filters)
  const descriptions = describeClientFilters(filters)

  const setNumber = (field: 'minScore' | 'minRating' | 'minReviews', rawValue: string, maximum: number) => {
    const parsed = Number(rawValue)
    const nextValue = Number.isFinite(parsed) ? Math.min(maximum, Math.max(0, parsed)) : 0
    onChange({ ...filters, [field]: nextValue })
  }

  const toggleContact = (contact: RequiredClientContact) => {
    const requiredContacts = filters.requiredContacts.includes(contact)
      ? filters.requiredContacts.filter((item) => item !== contact)
      : [...filters.requiredContacts, contact]
    onChange({ ...filters, requiredContacts })
  }

  return (
    <>
      <section
        className="client-retention-panel"
        id="client-retention-filter-panel"
        aria-labelledby="client-retention-filter-title"
        hidden={!isOpen}
      >
          <header className="retention-panel-header">
            <span className="retention-panel-icon"><SlidersHorizontal size={20} /></span>
            <div>
              <h2 id="client-retention-filter-title">Кто остаётся в списке</h2>
              <p>Все выбранные условия применяются одновременно.</p>
            </div>
            <button type="button" className="retention-close" onClick={onClose} aria-label="Свернуть фильтр">
              <X size={18} />
            </button>
          </header>

          <div className="retention-filter-grid">
            <fieldset className="retention-filter-section retention-score-section">
              <legend>Качество лида</legend>
              <div className="retention-score-presets" aria-label="Быстрый выбор очков лида">
                {scorePresets.map((score) => (
                  <button
                    type="button"
                    className={filters.minScore === score ? 'active' : ''}
                    aria-pressed={filters.minScore === score}
                    onClick={() => onChange({ ...filters, minScore: score })}
                    key={score}
                  >
                    {score ? `${score}+ очков` : 'Без минимума'}
                  </button>
                ))}
              </div>
              <div className="retention-number-grid">
                <label>
                  <span>Минимум очков лида</span>
                  <input
                    type="number"
                    min="0"
                    max="23"
                    step="1"
                    value={filters.minScore}
                    onChange={(event) => setNumber('minScore', event.target.value, 23)}
                  />
                </label>
                <label>
                  <span>Рейтинг бизнеса от</span>
                  <input
                    type="number"
                    min="0"
                    max="5"
                    step="0.1"
                    value={filters.minRating}
                    onChange={(event) => setNumber('minRating', event.target.value, 5)}
                  />
                </label>
                <label>
                  <span>Отзывов от</span>
                  <input
                    type="number"
                    min="0"
                    max="100000"
                    step="1"
                    value={filters.minReviews}
                    onChange={(event) => setNumber('minReviews', event.target.value, 100000)}
                  />
                </label>
              </div>
            </fieldset>

            <fieldset className="retention-filter-section">
              <legend>Обязательные контакты</legend>
              <p className="retention-section-hint">Клиент должен иметь каждый отмеченный канал.</p>
              <div className="retention-contact-grid">
                {contactOptions.map((option) => {
                  const checked = filters.requiredContacts.includes(option.value)
                  return (
                    <label className={checked ? 'active' : ''} key={option.value}>
                      <input
                        type="checkbox"
                        aria-label={option.label}
                        checked={checked}
                        onChange={() => toggleContact(option.value)}
                      />
                      <span className="retention-checkmark">{checked && <Check size={14} />}</span>
                      <span><strong>{option.label}</strong><small>{option.hint}</small></span>
                    </label>
                  )
                })}
              </div>
            </fieldset>

            <fieldset className="retention-filter-section retention-segments-section">
              <legend>Сайт и AI-текст</legend>
              <SegmentedFilter<ClientWebsiteFilter>
                label="Наличие сайта"
                value={filters.website}
                options={[
                  { value: 'any', label: 'Любой' },
                  { value: 'missing', label: 'Без сайта' },
                  { value: 'present', label: 'С сайтом' },
                ]}
                onChange={(website) => onChange({ ...filters, website })}
              />
              <SegmentedFilter<ClientAiMessageFilter>
                label="Текст для клиента"
                value={filters.aiMessage}
                options={[
                  { value: 'any', label: 'Любой' },
                  { value: 'missing', label: 'Не создан' },
                  { value: 'generated', label: 'Создан' },
                ]}
                onChange={(aiMessage) => onChange({ ...filters, aiMessage })}
              />
            </fieldset>
          </div>
      </section>

      {activeCount > 0 && (
        <div className="client-retention-summary" aria-live="polite">
          <div className="retention-summary-count">
            <strong>Осталось {visibleCount} из {totalCount}</strong>
            <span>{visibleCount ? 'Можно работать с этой выборкой' : 'Ослабьте одно из условий'}</span>
          </div>
          <div className="retention-summary-chips">
            {descriptions.map((description) => <span key={description}>{description}</span>)}
          </div>
          <button type="button" onClick={onReset} aria-label="Сбросить фильтр">
            <RotateCcw size={16} />Сбросить
          </button>
        </div>
      )}
    </>
  )
}

function SegmentedFilter<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: Array<{ value: T; label: string }>
  onChange: (value: T) => void
}) {
  return (
    <div className="retention-segmented-field">
      <span>{label}</span>
      <div role="group" aria-label={label}>
        {options.map((option) => (
          <button
            type="button"
            className={value === option.value ? 'active' : ''}
            aria-pressed={value === option.value}
            onClick={() => onChange(option.value)}
            key={option.value}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}
