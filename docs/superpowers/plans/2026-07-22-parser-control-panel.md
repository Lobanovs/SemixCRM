# Parser Control Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести основные настройки парсера в постоянно видимую desktop-панель и гарантировать сохранение актуальных значений перед каждым запуском.

**Architecture:** `ParserControlPanel` отображает и редактирует draft настроек, а `ParserNichesDialog` решает только задачу выбора ниш. `ClientsPage` хранит draft и сохранённый снимок, использует общий API-модуль для PUT настроек и запускает POST только после успешного PUT.

**Tech Stack:** React 19, TypeScript, CSS, Lucide React, Vitest, Testing Library, FastAPI API.

## Global Constraints

- Основной целевой viewport — desktop от 1024 px.
- Стартовая страница 2GIS ограничена диапазоном 1–999.
- Лимит на нишу и источник ограничен диапазоном 1–50.
- Запуск парсера всегда выполняет `PUT /api/parser/settings` перед `POST /api/clients/parse`.
- Отдельная мобильная композиция не создаётся, но горизонтальный overflow недопустим.
- Backend-схема настроек и внешний источник Яндекс Карт не меняются.
- Все изменения коммитятся и отправляются в `main` GitHub-репозитория пользователя.

---

### Task 1: Frontend Regression Test Harness

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Create: `vite.config.ts`
- Create: `src/test/setup.ts`
- Create: `src/pages/ClientsPage.test.tsx`

**Interfaces:**
- Consumes: существующий default export `ClientsPage`.
- Produces: команда `npm run test:frontend` и browser-like jsdom environment.

- [ ] **Step 1: Install the test dependencies**

Run:

```powershell
npm install --save-dev vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

Expected: `package.json` and `package-lock.json` contain the five dev dependencies.

- [ ] **Step 2: Configure Vitest**

Create `vite.config.ts` with React and jsdom:

```ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
```

Create `src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

Add the exact script to `package.json`:

```json
"test:frontend": "vitest run"
```

- [ ] **Step 3: Write failing UI and request-order tests**

In `src/pages/ClientsPage.test.tsx`, mock the four initial GET endpoints with empty client data and saved 2GIS settings. Add tests that assert:

```ts
expect(await screen.findByRole('spinbutton', { name: 'Стартовая страница 2GIS' })).toBeVisible()
```

Then change the field to `4`, click `Сохранить настройки`, and assert that the PUT JSON contains `start_page: 4`. In a separate test click `Запустить парсер` and assert that the first two mutation requests are `PUT /api/parser/settings` and `POST /api/clients/parse` in that order.

- [ ] **Step 4: Run tests and verify RED**

Run:

```powershell
npm run test:frontend -- --reporter=verbose
```

Expected: FAIL because the start-page spinbutton and save action are still hidden inside the closed settings modal, and current launch performs POST without PUT.

### Task 2: Parser Settings Domain and Visible Panel

**Files:**
- Create: `src/pages/parserSettings.ts`
- Create: `src/pages/ParserControlPanel.tsx`
- Modify: `src/pages/ClientsPage.tsx`
- Test: `src/pages/ClientsPage.test.tsx`

**Interfaces:**
- Produces: `ParserSettings`, `persistParserSettings(settings, request?)`, `startParserWithSettings(settings, request?)` from `src/pages/parserSettings.ts`.
- Produces: `ParserControlPanel` with `settings`, `savedSettings`, `stats`, `isSaving`, `isParsing`, `feedback`, `onChange`, `onSave`, and `onRun` props.
- Consumes: `PUT /api/parser/settings` response and `POST /api/clients/parse` response.

- [ ] **Step 1: Add the parser settings domain module**

Define and export:

```ts
export type ParserSettings = {
  city: string
  niches: string[]
  sources: string[]
  limit: number
  start_page: number
  updated_at?: string
}

export async function persistParserSettings(settings: ParserSettings, request: typeof fetch = fetch): Promise<ParserSettings>

export async function startParserWithSettings(settings: ParserSettings, request: typeof fetch = fetch): Promise<{ settings: ParserSettings; jobId: string }>
```

`startParserWithSettings()` must await `persistParserSettings()`, then send the returned settings to `/api/clients/parse`. A non-OK response or missing `job_id` throws a Russian user-facing error.

- [ ] **Step 2: Build the always-visible control panel**

Create a semantic panel containing:

- city `<select>`;
- source toggle buttons with `aria-pressed`;
- niche summary and `Выбрать ниши` button;
- number input labelled `Стартовая страница 2GIS` with `−` and `+` buttons;
- limit range plus exact numeric value;
- `Сохранить настройки` and `Запустить парсер` actions;
- inline `role="status"` or `role="alert"` feedback.

The niche dialog copies the current array into local state, applies it only through `onChange()` after pressing `Применить ниши`, and closes without changes on `Отмена`.

- [ ] **Step 3: Connect draft, save, and run state in ClientsPage**

Keep both:

```ts
const [parserSettings, setParserSettings] = useState(defaultParserSettings)
const [savedParserSettings, setSavedParserSettings] = useState(defaultParserSettings)
```

`refreshBackend()` assigns the GET settings response to both states. Manual save calls `persistParserSettings(parserSettings)`. Run calls `startParserWithSettings(parserSettings)`, assigns the returned saved settings, and polls the returned `jobId` using the existing job-status loop.

Remove the old `showParserSettings` state and `ParserSettingsModal`. Replace the old parser summary/actions markup with `ParserControlPanel`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
npm run test:frontend -- --reporter=verbose
```

Expected: all parser panel tests PASS with PUT before POST.

### Task 3: Desktop Visual Polish and Verification

**Files:**
- Modify: `src/styles.css`
- Modify: `README.md`
- Test: `src/pages/ClientsPage.test.tsx`

**Interfaces:**
- Consumes: class names emitted by `ParserControlPanel` and `ParserNichesDialog`.
- Produces: a readable 330–380 px sidebar panel with 44 px controls and no nested settings scroll.

- [ ] **Step 1: Style the desktop panel**

Add focused `.parser-control-*` rules using the existing Semix tokens: two-column compact field grid where width permits, 44 px inputs/buttons, blue focus rings, segmented sources, dirty/saved state badge, explicit primary/secondary actions, and dark-theme equivalents. Keep the existing breakpoint collapse at 1180 px and prevent horizontal overflow.

- [ ] **Step 2: Reduce the modal to niche selection only**

Reuse the existing fixed modal header/footer pattern, remove nested outer form scrolling, and keep only the search plus one scrollable niche grid. Footer actions are `Отмена` and `Применить ниши`.

- [ ] **Step 3: Update README**

Document that parser settings are edited directly in the client parser card and that pressing launch automatically saves the current city, niches, sources, limit, and 2GIS start page before creating the job.

- [ ] **Step 4: Run automated verification**

Run:

```powershell
npm run test:frontend -- --reporter=verbose
backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
npm run build
```

Expected: frontend tests PASS, 43 backend tests PASS, TypeScript and Vite build exit 0.

- [ ] **Step 5: Run desktop browser verification**

At `http://127.0.0.1:5173/`, open «Волк с Уолл-стрит» and verify without opening a settings modal:

1. page input is visible;
2. enter page `4`;
3. save and confirm `GET /api/parser/settings` reports `start_page: 4`;
4. set limit `1`, press launch, confirm the job appears and receives a status;
5. restore the diagnostic settings after the run.

- [ ] **Step 6: Commit and push implementation**

```text
git add package.json package-lock.json vite.config.ts src/test/setup.ts src/pages/ClientsPage.test.tsx src/pages/parserSettings.ts src/pages/ParserControlPanel.tsx src/pages/ClientsPage.tsx src/styles.css README.md
git commit -m "fix: make parser controls usable"
git push origin main
```
