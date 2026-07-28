import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('Semix CRM favicon', () => {
  it('подключает фирменную SVG-иконку во вкладку браузера', () => {
    const html = readFileSync(resolve('index.html'), 'utf8')
    const favicon = readFileSync(resolve('public/favicon.svg'), 'utf8')

    expect(html).toContain('<link rel="icon" type="image/svg+xml" href="/favicon.svg" />')
    expect(favicon).toContain('aria-label="Semix CRM"')
    expect(favicon).toContain('#2563EB')
    expect(favicon).toContain('#7C3AED')
  })
})
