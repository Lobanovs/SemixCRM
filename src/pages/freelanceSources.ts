import type { UiAccent } from '../components/DashboardUi'
import flIcon from '../assets/freelance/fl.webp'
import freelanceRuIcon from '../assets/freelance/freelance-ru.webp'
import kworkIcon from '../assets/freelance/kwork.webp'
import profiIcon from '../assets/freelance/profi.webp'
import youdoIcon from '../assets/freelance/youdo.webp'

export const FREELANCE_SOURCE_KEYS = ['kwork', 'fl', 'freelance_ru', 'profi', 'youdo'] as const
export const BROWSER_SOURCE_KEYS = ['profi', 'youdo'] as const

export type FreelanceSourceKey = (typeof FREELANCE_SOURCE_KEYS)[number]

type FreelanceSourceMeta = {
  label: string
  icon: string
  accent: UiAccent
  url: string
}

export const FREELANCE_SOURCE_META: Record<FreelanceSourceKey, FreelanceSourceMeta> = {
  kwork: {
    label: 'Kwork',
    icon: kworkIcon,
    accent: 'green',
    url: 'https://kwork.ru/projects',
  },
  fl: {
    label: 'FL.ru',
    icon: flIcon,
    accent: 'blue',
    url: 'https://www.fl.ru/projects/',
  },
  freelance_ru: {
    label: 'Freelance.ru',
    icon: freelanceRuIcon,
    accent: 'purple',
    url: 'https://freelance.ru/task',
  },
  profi: {
    label: 'Profi.ru',
    icon: profiIcon,
    accent: 'pink',
    url: 'https://profi.ru/backoffice/n.php',
  },
  youdo: {
    label: 'YouDo',
    icon: youdoIcon,
    accent: 'blue',
    url: 'https://youdo.com/tasks',
  },
}

export function isFreelanceSourceKey(source: string): source is FreelanceSourceKey {
  return FREELANCE_SOURCE_KEYS.includes(source as FreelanceSourceKey)
}

export function freelanceSourceLabel(source: string) {
  if (source === 'manual') return 'Вручную'
  return isFreelanceSourceKey(source) ? FREELANCE_SOURCE_META[source].label : source
}
