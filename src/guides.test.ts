import { describe, expect, it } from 'vitest'

import { CLIENTS_GUIDE, FREELANCE_GUIDE, HOME_GUIDE, JOBS_GUIDE, PROJECTS_GUIDE, SCHEDULE_GUIDE } from './guides'
import type { GuideStep } from './components/PageGuide'

const ALL_GUIDES: Record<string, GuideStep[]> = {
  home: HOME_GUIDE,
  projects: PROJECTS_GUIDE,
  jobs: JOBS_GUIDE,
  freelance: FREELANCE_GUIDE,
  schedule: SCHEDULE_GUIDE,
  clients: CLIENTS_GUIDE,
}

// Исходники читаются через Vite, а не через node:fs: так тест обходится
// без @types/node и остаётся под проверкой tsc вместе с остальным кодом.
const SOURCES = import.meta.glob('./**/*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

const ANCHOR_PATTERN = /data-guide="([\w-]+)"/g

function anchorsInMarkup(): Set<string> {
  const anchors = new Set<string>()
  for (const [path, source] of Object.entries(SOURCES)) {
    if (path.endsWith('.test.tsx')) continue
    for (const match of source.matchAll(ANCHOR_PATTERN)) anchors.add(match[1])
  }
  return anchors
}

/** Якоря, которые инструкции просят подсветить, вместе с местом объявления. */
function anchorsInGuides(): Map<string, string> {
  const anchors = new Map<string, string>()
  for (const [section, steps] of Object.entries(ALL_GUIDES)) {
    for (const step of steps) {
      const match = step.selector?.match(/data-guide="([\w-]+)"/)
      if (match) anchors.set(match[1], `${section}: ${step.title}`)
    }
  }
  return anchors
}

describe('инструкции разделов', () => {
  it('каждый шаг тура указывает на существующий якорь в разметке', () => {
    const markup = anchorsInMarkup()
    const missing = [...anchorsInGuides()]
      .filter(([anchor]) => !markup.has(anchor))
      .map(([anchor, where]) => `${anchor} (${where})`)

    expect(missing).toEqual([])
  })

  it('каждый якорь в разметке используется хотя бы одним шагом', () => {
    const wanted = new Set(anchorsInGuides().keys())
    const orphans = [...anchorsInMarkup()].filter((anchor) => !wanted.has(anchor))

    expect(orphans).toEqual([])
  })

  it('у каждого раздела есть шаги, и в каждом шаге заполнены заголовок и текст', () => {
    for (const [section, steps] of Object.entries(ALL_GUIDES)) {
      expect(steps.length, `у раздела ${section} нет шагов`).toBeGreaterThan(0)
      for (const step of steps) {
        expect(step.title.trim(), `пустой заголовок в разделе ${section}`).not.toBe('')
        expect(step.body.trim().length, `слишком короткий текст: ${section} / ${step.title}`).toBeGreaterThan(40)
      }
    }
  })

  it('селекторы шагов не повторяются внутри одного раздела', () => {
    for (const [section, steps] of Object.entries(ALL_GUIDES)) {
      const selectors = steps.map((step) => step.selector).filter(Boolean)
      expect(new Set(selectors).size, `повторяющийся селектор в разделе ${section}`).toBe(selectors.length)
    }
  })

  it('объясняет безопасный сценарий ИИ-планирования недели', () => {
    const step = SCHEDULE_GUIDE.find((item) => item.selector === '[data-guide="schedule-ai-plan"]')

    expect(step).toBeDefined()
    expect(step?.body).toMatch(/черновик/i)
    expect(step?.body).toMatch(/выбрать/i)
    expect(step?.body).toMatch(/подтвержден/i)
  })
})
