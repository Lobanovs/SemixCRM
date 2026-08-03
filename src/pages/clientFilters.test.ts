import { describe, expect, it } from 'vitest'

import {
  DEFAULT_CLIENT_RETENTION_FILTERS,
  countActiveClientFilters,
  describeClientFilters,
  matchesClientRetentionFilters,
} from './clientFilters'

const client = {
  score: 15,
  rating: 4.8,
  reviews: 120,
  phone: '+7 999 000-00-00',
  website: '',
  contacts: [{ type: 'telegram', value: '@lead' }],
  aiMessageStatus: 'ready',
}

describe('client retention filters', () => {
  it('keeps a client on the inclusive lead score boundary', () => {
    expect(matchesClientRetentionFilters(client, { ...DEFAULT_CLIENT_RETENTION_FILTERS, minScore: 15 })).toBe(true)
    expect(matchesClientRetentionFilters({ ...client, score: 14 }, { ...DEFAULT_CLIENT_RETENTION_FILTERS, minScore: 15 })).toBe(false)
  })

  it('requires every selected contact channel', () => {
    const filters = { ...DEFAULT_CLIENT_RETENTION_FILTERS, requiredContacts: ['telegram', 'whatsapp'] as const }

    expect(matchesClientRetentionFilters(client, filters)).toBe(false)
    expect(matchesClientRetentionFilters({
      ...client,
      contacts: [...client.contacts, { type: 'whatsapp', value: '+79990000000' }],
    }, filters)).toBe(true)
  })

  it('uses the phone field when normalized contacts do not contain a phone', () => {
    const filters = { ...DEFAULT_CLIENT_RETENTION_FILTERS, requiredContacts: ['phone'] as const }

    expect(matchesClientRetentionFilters(client, filters)).toBe(true)
    expect(matchesClientRetentionFilters({ ...client, phone: '' }, filters)).toBe(false)
  })

  it('combines rating reviews website and AI requirements', () => {
    const filters = {
      ...DEFAULT_CLIENT_RETENTION_FILTERS,
      minRating: 4.5,
      minReviews: 100,
      website: 'missing' as const,
      aiMessage: 'generated' as const,
    }

    expect(matchesClientRetentionFilters(client, filters)).toBe(true)
    expect(matchesClientRetentionFilters({ ...client, rating: null }, filters)).toBe(false)
    expect(matchesClientRetentionFilters({ ...client, reviews: 99 }, filters)).toBe(false)
    expect(matchesClientRetentionFilters({ ...client, website: 'https://company.ru' }, filters)).toBe(false)
    expect(matchesClientRetentionFilters({ ...client, aiMessageStatus: 'missing' }, filters)).toBe(false)
  })

  it('does not treat messaging or social links as a business website', () => {
    const filters = { ...DEFAULT_CLIENT_RETENTION_FILTERS, website: 'missing' as const }

    expect(matchesClientRetentionFilters({ ...client, website: 'https://t.me/lead' }, filters)).toBe(true)
    expect(matchesClientRetentionFilters({ ...client, website: 'https://wa.me/79990000000' }, filters)).toBe(true)
    expect(matchesClientRetentionFilters({ ...client, website: 'https://vk.com/company' }, filters)).toBe(true)
  })

  it('treats stale AI text as generated and supports missing text', () => {
    expect(matchesClientRetentionFilters(
      { ...client, aiMessageStatus: 'stale' },
      { ...DEFAULT_CLIENT_RETENTION_FILTERS, aiMessage: 'generated' },
    )).toBe(true)
    expect(matchesClientRetentionFilters(
      { ...client, aiMessageStatus: 'missing' },
      { ...DEFAULT_CLIENT_RETENTION_FILTERS, aiMessage: 'missing' },
    )).toBe(true)
  })

  it('counts and describes every active criterion', () => {
    const filters = {
      ...DEFAULT_CLIENT_RETENTION_FILTERS,
      minScore: 15,
      minRating: 4.5,
      minReviews: 100,
      requiredContacts: ['telegram', 'whatsapp'] as const,
      website: 'missing' as const,
      aiMessage: 'generated' as const,
    }

    expect(countActiveClientFilters(filters)).toBe(7)
    expect(describeClientFilters(filters)).toEqual([
      'Очки лида от 15',
      'Рейтинг от 4,5',
      'Отзывов от 100',
      'Есть Telegram',
      'Есть WhatsApp',
      'Без сайта',
      'Текст создан',
    ])
  })
})
