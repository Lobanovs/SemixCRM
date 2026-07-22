import { describe, expect, it } from 'vitest'

import { BROWSER_SOURCE_KEYS, FREELANCE_SOURCE_KEYS, FREELANCE_SOURCE_META } from './freelanceSources'


describe('freelance source metadata', () => {
  it('defines five distinct source badges without Workzilla', () => {
    expect(FREELANCE_SOURCE_KEYS).toEqual(['kwork', 'fl', 'freelance_ru', 'profi', 'youdo'])
    expect(BROWSER_SOURCE_KEYS).toEqual(['profi', 'youdo'])
    expect(new Set(FREELANCE_SOURCE_KEYS.map((key) => FREELANCE_SOURCE_META[key].icon)).size).toBe(5)
    expect(JSON.stringify(FREELANCE_SOURCE_META).toLowerCase()).not.toContain('workzilla')
  })
})
