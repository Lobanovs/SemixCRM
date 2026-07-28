# Semix CRM Favicon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить узнаваемую SVG-иконку Semix CRM во вкладку браузера.

**Architecture:** Статический SVG хранится в Vite-каталоге `public` и подключается обычным favicon-link в `index.html`. Отдельный Vitest-тест читает оба файла и защищает подключение и ключевые элементы знака от случайного удаления.

**Tech Stack:** SVG, HTML, Vite, Vitest, Node.js `fs`.

## Global Constraints

- Знак: белая `S` и фиолетовая AI-искра на синем скруглённом квадрате.
- Иконка должна оставаться различимой в размере 16×16 пикселей.
- Не добавлять растровые изображения и новые зависимости.
- Заголовок вкладки остаётся `Semix CRM`.

---

### Task 1: Подключить и проверить favicon

**Files:**
- Create: `src/favicon.test.ts`
- Create: `public/favicon.svg`
- Modify: `index.html`

**Interfaces:**
- Consumes: Vite автоматически публикует содержимое `public` от корня сайта.
- Produces: `/favicon.svg`, подключённый через `<link rel="icon" type="image/svg+xml" href="/favicon.svg" />`.

- [ ] **Step 1: Write the failing test**

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm.cmd run test:frontend -- src/favicon.test.ts`

Expected: FAIL because `public/favicon.svg` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `public/favicon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Semix CRM">
  <rect width="64" height="64" rx="14" fill="#2563EB"/>
  <path fill="#fff" d="M41 20c-2.6-3-6-4.3-10-4.3-5.3 0-8.7 2.1-8.7 5.4 0 3.1 2.4 4.6 8.1 5.8l3.4.8c8 1.8 11.8 5.4 11.8 11 0 7.2-5.8 11.8-14.8 11.8-7.4 0-13.2-2.6-16.8-7.5l6.1-4.5c2.6 3.5 6.2 5.2 10.9 5.2 4.5 0 7.2-1.8 7.2-4.6 0-2.6-2.2-4.1-7.4-5.3l-3.5-.8c-8-1.8-12.2-5.6-12.2-11.6 0-7.3 6.1-12 15.5-12 6.6 0 12.1 2.1 16.2 6.4z"/>
  <circle cx="50" cy="14" r="10" fill="#7C3AED" stroke="#fff" stroke-width="2"/>
  <path fill="#fff" d="M50 7.5c.6 3.7 2.3 5.4 6 6-3.7.6-5.4 2.3-6 6-.6-3.7-2.3-5.4-6-6 3.7-.6 5.4-2.3 6-6z"/>
</svg>
```

Add inside `<head>` in `index.html`:

```html
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
```

- [ ] **Step 4: Run test and production build**

Run: `npm.cmd run test:frontend -- src/favicon.test.ts`

Expected: PASS.

Run: `npm.cmd run build`

Expected: exit code 0 and `dist/favicon.svg` exists.

- [ ] **Step 5: Verify in browser**

Open `http://127.0.0.1:5173/`, verify `document.title === "Semix CRM"`, the favicon link resolves to `/favicon.svg`, and the response status is 200.

- [ ] **Step 6: Commit**

```bash
git add src/favicon.test.ts public/favicon.svg index.html
git commit -m "feat: add Semix CRM browser icon"
git push origin main
```

