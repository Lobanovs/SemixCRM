export type RequiredClientContact = 'telegram' | 'whatsapp' | 'phone' | 'email'
export type ClientWebsiteFilter = 'any' | 'missing' | 'present'
export type ClientAiMessageFilter = 'any' | 'missing' | 'generated'

export type ClientRetentionFilterState = {
  minScore: number
  minRating: number
  minReviews: number
  requiredContacts: readonly RequiredClientContact[]
  website: ClientWebsiteFilter
  aiMessage: ClientAiMessageFilter
}

export type FilterableClient = {
  score: number
  rating: number | null
  reviews: number | null
  phone: string
  website: string
  contacts: ReadonlyArray<{ type: string; value: string }>
  aiMessageStatus: string
}

export const DEFAULT_CLIENT_RETENTION_FILTERS: ClientRetentionFilterState = {
  minScore: 0,
  minRating: 0,
  minReviews: 0,
  requiredContacts: [],
  website: 'any',
  aiMessage: 'any',
}

const channelLabels: Record<RequiredClientContact, string> = {
  telegram: 'Telegram',
  whatsapp: 'WhatsApp',
  phone: 'телефон',
  email: 'e-mail',
}

const socialWebsitePattern = /(?:^|\.|\/\/)(?:t\.me|telegram\.me|telegram\.org|wa\.me|whatsapp\.com|vk\.com|instagram\.com|facebook\.com|youtube\.com)(?:\/|$)/i

export function hasBusinessWebsite(value: string): boolean {
  const normalized = value.trim()
  return Boolean(normalized) && !socialWebsitePattern.test(normalized)
}

export function matchesClientRetentionFilters(
  client: FilterableClient,
  filters: ClientRetentionFilterState,
): boolean {
  if (client.score < filters.minScore) return false
  if (filters.minRating > 0 && (client.rating === null || client.rating < filters.minRating)) return false
  if ((client.reviews ?? 0) < filters.minReviews) return false

  const contactTypes = new Set(client.contacts.map((contact) => contact.type.toLocaleLowerCase('en')))
  if (client.phone.trim()) contactTypes.add('phone')
  if (!filters.requiredContacts.every((contact) => contactTypes.has(contact))) return false

  const hasWebsite = hasBusinessWebsite(client.website)
  if (filters.website === 'missing' && hasWebsite) return false
  if (filters.website === 'present' && !hasWebsite) return false

  const hasGeneratedMessage = client.aiMessageStatus === 'ready' || client.aiMessageStatus === 'stale'
  if (filters.aiMessage === 'missing' && hasGeneratedMessage) return false
  if (filters.aiMessage === 'generated' && !hasGeneratedMessage) return false

  return true
}

export function countActiveClientFilters(filters: ClientRetentionFilterState): number {
  return Number(filters.minScore > 0)
    + Number(filters.minRating > 0)
    + Number(filters.minReviews > 0)
    + filters.requiredContacts.length
    + Number(filters.website !== 'any')
    + Number(filters.aiMessage !== 'any')
}

function formatDecimal(value: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)
}

export function describeClientFilters(filters: ClientRetentionFilterState): string[] {
  const descriptions: string[] = []
  if (filters.minScore > 0) descriptions.push(`Очки лида от ${formatDecimal(filters.minScore)}`)
  if (filters.minRating > 0) descriptions.push(`Рейтинг от ${formatDecimal(filters.minRating)}`)
  if (filters.minReviews > 0) descriptions.push(`Отзывов от ${formatDecimal(filters.minReviews)}`)
  filters.requiredContacts.forEach((contact) => descriptions.push(`Есть ${channelLabels[contact]}`))
  if (filters.website === 'missing') descriptions.push('Без сайта')
  if (filters.website === 'present') descriptions.push('Есть сайт')
  if (filters.aiMessage === 'missing') descriptions.push('Текст не создан')
  if (filters.aiMessage === 'generated') descriptions.push('Текст создан')
  return descriptions
}
