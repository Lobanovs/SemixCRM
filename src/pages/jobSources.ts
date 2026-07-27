import type { UiAccent } from '../components/DashboardUi'

export const JOB_SOURCE_KEYS = ['hh', 'habr', 'telegram', 'remoteok', 'remotive', 'weworkremotely'] as const

export type JobSourceKey = (typeof JOB_SOURCE_KEYS)[number]

type JobSourceMeta = {
  label: string
  short: string
  tone: UiAccent
  url: string
}

export const JOB_SOURCE_META: Record<string, JobSourceMeta> = {
  hh: {
    label: 'hh.ru',
    short: 'HH',
    tone: 'red',
    url: 'https://hh.ru/search/vacancy',
  },
  habr: {
    label: 'Хабр Карьера',
    short: 'Х',
    tone: 'blue',
    url: 'https://career.habr.com/vacancies',
  },
  telegram: {
    label: 'Telegram',
    short: 'TG',
    tone: 'cyan',
    url: 'https://t.me',
  },
  remoteok: {
    label: 'RemoteOK',
    short: 'OK',
    tone: 'green',
    url: 'https://remoteok.com',
  },
  remotive: {
    label: 'Remotive',
    short: 'RM',
    tone: 'purple',
    url: 'https://remotive.com/remote-jobs',
  },
  weworkremotely: {
    label: 'We Work Remotely',
    short: 'WW',
    tone: 'orange',
    url: 'https://weworkremotely.com',
  },
}

export function isJobSourceKey(source: string): source is JobSourceKey {
  return JOB_SOURCE_KEYS.includes(source as JobSourceKey)
}

export function jobSourceLabel(source: string) {
  if (source === 'manual') return 'Вручную'
  return isJobSourceKey(source) ? JOB_SOURCE_META[source].label : source
}
