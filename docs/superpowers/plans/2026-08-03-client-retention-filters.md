# Client Retention Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an inline “Кто остаётся” filter that keeps only clients matching selected sales criteria without modifying stored data.

**Architecture:** Pure matching and summary rules live in `clientFilters.ts`; a focused React component renders the disclosure panel; `ClientsPage` owns filter state and combines it with existing list filters. All changes are frontend-only.

**Tech Stack:** React 19, TypeScript, Lucide React, Vitest, Testing Library, CSS.

## Global Constraints

- Lead score is an inclusive integer threshold from 0 through 23.
- Business rating is an inclusive threshold from 0 through 5.
- Multiple required contact channels use logical AND.
- Website and AI-message filters have explicit three-state values.
- Filtering must never call archive or delete APIs.
- Controls must remain keyboard accessible in light, dark, and premium-dark themes.

---

### Task 1: Pure client matching rules

**Files:**
- Create: `src/pages/clientFilters.test.ts`
- Create: `src/pages/clientFilters.ts`

**Interfaces:**
- Produces: `ClientRetentionFilterState`, `DEFAULT_CLIENT_RETENTION_FILTERS`, `matchesClientRetentionFilters`, `countActiveClientFilters`, and `describeClientFilters`.

- [ ] **Step 1: Write the failing matching tests**

Cover an inclusive 15-point threshold, required-channel AND behavior, absent rating, minimum reviews, social links not counting as websites, and generated AI states:

```ts
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
  phone: '+79990000000',
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
  })

  it('combines rating reviews website and AI requirements', () => {
    const filters = { ...DEFAULT_CLIENT_RETENTION_FILTERS, minRating: 4.5, minReviews: 100, website: 'missing' as const, aiMessage: 'generated' as const }
    expect(matchesClientRetentionFilters(client, filters)).toBe(true)
    expect(matchesClientRetentionFilters({ ...client, rating: null }, filters)).toBe(false)
    expect(matchesClientRetentionFilters({ ...client, website: 'https://company.ru' }, filters)).toBe(false)
  })

  it('does not treat a Telegram link as a business website', () => {
    expect(matchesClientRetentionFilters({ ...client, website: 'https://t.me/lead' }, { ...DEFAULT_CLIENT_RETENTION_FILTERS, website: 'missing' })).toBe(true)
  })

  it('counts and describes active criteria', () => {
    const filters = { ...DEFAULT_CLIENT_RETENTION_FILTERS, minScore: 15, requiredContacts: ['telegram'] as const, website: 'missing' as const }
    expect(countActiveClientFilters(filters)).toBe(3)
    expect(describeClientFilters(filters)).toEqual(['Очки лида от 15', 'Есть Telegram', 'Без сайта'])
  })
})
```

- [ ] **Step 2: Run the test and verify RED**

Run: `npm run test:frontend -- src/pages/clientFilters.test.ts`

Expected: FAIL because `./clientFilters` does not exist.

- [ ] **Step 3: Implement the minimal pure module**

Create the filter types, default state, real-website guard, contact matcher, numeric threshold checks, active-count function, and Russian description labels. Clamp numeric values at the component boundary; keep the matcher side-effect free.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `npm run test:frontend -- src/pages/clientFilters.test.ts`

Expected: all tests in `clientFilters.test.ts` PASS.

- [ ] **Step 5: Commit and push**

```powershell
git add -- src/pages/clientFilters.ts src/pages/clientFilters.test.ts
git commit -m "feat: add client retention filter rules"
git push origin main
```

### Task 2: Inline filter panel and page integration

**Files:**
- Create: `src/pages/ClientRetentionFilters.tsx`
- Modify: `src/pages/ClientsPage.tsx`
- Modify: `src/pages/ClientsPage.test.tsx`

**Interfaces:**
- Consumes: all exports from `clientFilters.ts`.
- Produces: `ClientRetentionFilters` component with `filters`, `visibleCount`, `totalCount`, `onChange`, and `onReset` props.

- [ ] **Step 1: Write a failing page behavior test**

Return three clients from the existing fetch mock: a 19-point Telegram lead, a 16-point phone-only lead, and a 9-point Telegram lead. Assert this sequence:

```ts
await user.click(await screen.findByRole('button', { name: /Кто остаётся/ }))
await user.click(screen.getByRole('button', { name: '15+ очков' }))
expect(screen.getByText('Осталось 2 из 3')).toBeVisible()
await user.click(screen.getByRole('checkbox', { name: 'Telegram' }))
expect(screen.getByText('Осталось 1 из 3')).toBeVisible()
expect(screen.getByRole('heading', { name: 'Лид с Telegram' })).toBeVisible()
expect(screen.queryByRole('heading', { name: 'Лид только с телефоном' })).not.toBeInTheDocument()
await user.click(screen.getByRole('button', { name: 'Сбросить фильтр' }))
expect(screen.getAllByRole('article')).toHaveLength(3)
```

Also assert that selecting both Telegram and WhatsApp keeps only clients having both, and that no DELETE request is made.

- [ ] **Step 2: Run the page test and verify RED**

Run: `npm run test:frontend -- src/pages/ClientsPage.test.tsx`

Expected: FAIL because the “Кто остаётся” control is missing.

- [ ] **Step 3: Build the filter component**

The component renders:

```tsx
<button type="button" aria-expanded={open} aria-controls="client-retention-filter-panel">
  <ListFilter size={18} />Кто остаётся
  {activeCount > 0 && <span>{activeCount}</span>}
</button>
```

Its inline panel contains score preset buttons `0`, `10+`, `15+`, `18+`; labeled numeric inputs for score, rating, and reviews; checkbox cards for Telegram, WhatsApp, phone, and e-mail; segmented buttons for website and AI state; helper text that all conditions apply together; and reset/close actions.

- [ ] **Step 4: Integrate state into `ClientsPage`**

Add `filters` state initialized with a fresh copy of `DEFAULT_CLIENT_RETENTION_FILTERS`, append `matchesClientRetentionFilters(client, filters)` to the existing `useMemo` predicate, include `filters` in its dependency list, and render the component after the toolbar so it receives `filtered.length` and `clients.length`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `npm run test:frontend -- src/pages/clientFilters.test.ts src/pages/ClientsPage.test.tsx`

Expected: both files PASS.

- [ ] **Step 6: Commit and push**

```powershell
git add -- src/pages/ClientRetentionFilters.tsx src/pages/ClientsPage.tsx src/pages/ClientsPage.test.tsx
git commit -m "feat: filter retained sales leads"
git push origin main
```

### Task 3: Visual polish and regression verification

**Files:**
- Modify: `src/styles.css`
- Modify: `src/premium-dark.css`

**Interfaces:**
- Consumes: class names rendered by `ClientRetentionFilters.tsx`.
- Produces: responsive light/dark/premium-dark panel styling with visible hover, active, focus, and disabled states.

- [ ] **Step 1: Add the panel styles**

Use the existing 8–16 px dense-dashboard spacing, 8–12 px radii, blue accent, Lucide icons, and 180 ms transitions. Keep the panel in normal document flow, use a responsive CSS grid for criteria, render selected channel cards with both a check icon and accent border, and ensure the summary chips wrap.

- [ ] **Step 2: Run focused and complete frontend tests**

Run: `npm run test:frontend -- src/pages/clientFilters.test.ts src/pages/ClientsPage.test.tsx`

Expected: focused tests PASS.

Run: `npm run test:frontend`

Expected: complete frontend suite PASS.

- [ ] **Step 3: Build and run backend regression tests**

Run: `npm run build`

Expected: TypeScript compilation and Vite production build PASS.

Run: `backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v`

Expected: complete backend suite PASS.

- [ ] **Step 4: Perform browser QA**

At `http://127.0.0.1:5173/`, open “Волк с Уолл-стрит”, verify 15+ and Telegram filtering, select multiple channels, reset, keyboard-focus every control, and inspect light and premium-dark themes at desktop width. Confirm no horizontal scrolling and no DELETE network request.

- [ ] **Step 5: Run final diff checks, commit, and push**

```powershell
git diff --check
git status --short
git add -- src/styles.css src/premium-dark.css
git commit -m "style: polish client retention filters"
git push origin main
```
