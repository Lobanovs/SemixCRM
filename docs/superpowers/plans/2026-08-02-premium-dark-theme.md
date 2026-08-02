# Premium Dark Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Semix CRM's inconsistent slate night mode with a coherent premium black theme without changing the light theme or application behavior.

**Architecture:** Keep `theme-dark` as the compatibility class and add an explicit `data-theme="premium-dark"` contract to the root shell. Load a dedicated token-driven `premium-dark.css` after all existing styles so one file owns the final dark palette and page-specific legacy rules cannot win the cascade.

**Tech Stack:** React 19, TypeScript, CSS, Vitest, Testing Library, Vite.

## Global Constraints

- Preserve `localStorage` key `semix-crm-theme` and values `dark` / `light`.
- Do not modify backend behavior, API payloads, user data, component layout, or light-theme colors.
- Use the existing Semix blue accent; do not introduce gold as a brand color.
- Keep text contrast suitable for desktop use and retain visible keyboard focus.
- Respect `prefers-reduced-motion`.
- Commit and push every completed project change to `origin/main`.

---

## File Structure

- `src/App.test.tsx`: verifies the premium dark-theme DOM contract and persistence.
- `src/App.tsx`: exposes the dark-theme marker on the existing root shell.
- `src/premium-dark.css`: owns all premium dark tokens and final component overrides.
- `src/main.tsx`: imports the premium stylesheet after the legacy stylesheet.
- `README.md`: documents the dedicated premium theme file and behavior.

### Task 1: Testable theme contract

**Files:**
- Modify: `src/App.test.tsx`
- Modify: `src/App.tsx`

**Interfaces:**
- Consumes: existing `isDark: boolean` state and `semix-crm-theme` localStorage key.
- Produces: root attribute `data-theme="premium-dark"` only when `isDark === true`.

- [ ] **Step 1: Write the failing test**

Add this test inside `describe('навигация приложения', ...)`:

```tsx
it('activates and persists the premium dark theme', async () => {
  vi.stubGlobal('fetch', createAppFetch())
  const { container } = render(<App />)
  const shell = container.querySelector('.app-shell')

  expect(shell).not.toHaveAttribute('data-theme')

  await userEvent.setup().click(screen.getByRole('button', { name: 'Включить тёмную тему' }))

  expect(shell).toHaveClass('theme-dark')
  expect(shell).toHaveAttribute('data-theme', 'premium-dark')
  expect(window.localStorage.getItem('semix-crm-theme')).toBe('dark')
})
```

- [ ] **Step 2: Run the test to prove it fails**

Run: `npm run test:frontend -- src/App.test.tsx`

Expected: FAIL because the shell has no `data-theme` attribute.

- [ ] **Step 3: Implement the root marker**

Change the application shell to:

```tsx
<div
  className={`app-shell ${isDark ? 'theme-dark' : ''}`}
  data-theme={isDark ? 'premium-dark' : undefined}
>
```

- [ ] **Step 4: Run the focused test**

Run: `npm run test:frontend -- src/App.test.tsx`

Expected: all `App.test.tsx` tests PASS.

- [ ] **Step 5: Commit and push**

```powershell
git add src/App.tsx src/App.test.tsx
git commit -m "test: define premium dark theme contract"
git push origin main
```

### Task 2: Premium black visual system

**Files:**
- Create: `src/premium-dark.css`
- Modify: `src/main.tsx`

**Interfaces:**
- Consumes: `.theme-dark[data-theme='premium-dark']` on `.app-shell`.
- Produces: CSS custom properties `--premium-*` and final dark overrides for shell, content, controls, status states, and page-specific components.

- [ ] **Step 1: Import the final theme layer**

Append this import after `./styles.css` in `src/main.tsx`:

```tsx
import './premium-dark.css'
```

- [ ] **Step 2: Define the semantic tokens**

Create `src/premium-dark.css` with this root:

```css
.theme-dark[data-theme='premium-dark'] {
  color-scheme: dark;
  --premium-canvas: #06080b;
  --premium-chrome: #080a0e;
  --premium-surface: #0d1015;
  --premium-surface-raised: #121720;
  --premium-surface-hover: #171d27;
  --premium-border: rgba(255, 255, 255, 0.085);
  --premium-border-strong: rgba(255, 255, 255, 0.145);
  --premium-text: #f7f9fc;
  --premium-text-soft: #d3d9e3;
  --premium-text-muted: #a0a9b8;
  --premium-accent: #4c8dff;
  --premium-accent-bright: #75a7ff;
  --premium-accent-soft: rgba(76, 141, 255, 0.13);
  --premium-focus: rgba(76, 141, 255, 0.28);
  --premium-shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
}
```

- [ ] **Step 3: Apply shell and navigation styling**

Add final selectors for `.app-shell`, `.workspace`, `.data-page`, `.schedule-page`, `.sidebar`, `.topbar`, `.brand`, `.nav-item`, `.nav-item.active`, `.search-box`, `.theme-toggle`, `.profile-button`, `.menu-toggle`, and `.help-card`. Use canvas/chrome for the shell, raised surfaces for controls, `--premium-border` for separators, and accent only on active/focus states.

- [ ] **Step 4: Apply shared content and control styling**

Cover cards/rows/panels, tables, toolbars, inputs, textareas, selects, chips, pagination, modal surfaces, backdrops, headings, primary/secondary copy, placeholders, and scrollbars. Inputs use `--premium-surface-raised`; focused controls use `--premium-accent` plus `0 0 0 3px var(--premium-focus)`.

- [ ] **Step 5: Apply page-specific styling**

Cover Settings (`.settings-*`, `.ai-*` connection cards), Useful Things (`.useful-*`), client outreach (`.client-message-modal`, `.ai-workspace-*`, `.ai-insight-*`, `.ai-compose-*`), parser/history/archive, schedule/calendar, jobs, projects, clients, and freelance classes already present in the legacy dark selectors. Keep success green, warning amber, destructive red, and informational blue distinguishable on black surfaces.

- [ ] **Step 6: Add interaction and reduced-motion rules**

Use 160-220 ms color/border/box-shadow transitions for hover and focus. Add:

```css
@media (prefers-reduced-motion: reduce) {
  .theme-dark[data-theme='premium-dark'] *,
  .theme-dark[data-theme='premium-dark'] *::before,
  .theme-dark[data-theme='premium-dark'] *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
```

- [ ] **Step 7: Run frontend tests and build**

Run: `npm run test:frontend`

Expected: all frontend tests PASS.

Run: `npm run build`

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 8: Commit and push**

```powershell
git add src/main.tsx src/premium-dark.css
git commit -m "feat: add premium black dark theme"
git push origin main
```

### Task 3: Browser QA and documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the completed premium theme.
- Produces: verified desktop presentation and updated repository documentation.

- [ ] **Step 1: Verify the dashboard in dark mode**

At `http://127.0.0.1:5173/`, enable dark mode and confirm the shell marker, canvas, sidebar, cards, active navigation, text hierarchy, hover, and focus styling. Read computed colors for the shell and primary card and confirm they match the premium tokens.

- [ ] **Step 2: Verify representative feature pages**

Open Settings, Useful Things, Clients, and Schedule. Confirm panels, rows, tables, forms, status badges, empty states, and destructive buttons no longer use the old blue-gray surface palette.

- [ ] **Step 3: Verify a modal and console**

Open one available dialog or client-message modal, confirm the backdrop and nested surfaces, close it without saving user data, and inspect browser logs for errors.

- [ ] **Step 4: Verify light-theme isolation**

Switch to light mode and confirm the root marker disappears and representative shell/card computed colors remain the existing light values. Switch back to dark mode for delivery.

- [ ] **Step 5: Update README**

Change the interface description to call the dark theme premium black, and update the source tree to include:

```text
├── premium-dark.css  # финальный слой премиальной чёрной темы
└── styles.css        # базовые стили, светлая тема и адаптивная вёрстка
```

- [ ] **Step 6: Run final verification**

Run: `npm run test:frontend && npm run build`

Expected: tests PASS and build succeeds.

Run: `git status --short --branch`

Expected: only the intended README change is pending before the final documentation commit.

- [ ] **Step 7: Commit and push**

```powershell
git add README.md
git commit -m "docs: document premium dark theme"
git push origin main
```
