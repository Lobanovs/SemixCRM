# Semix CRM Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a dependable desktop CRM release with a working action center, safe API calls, scalable long lists, editable AI profile, and downloadable SQLite backups.

**Architecture:** Keep the current React/FastAPI/SQLite structure and add narrow reusable boundaries instead of rewriting modules. The backend exposes read-only dashboard aggregation and safe backup endpoints; the frontend centralizes transport in `src/api.ts`, progressively renders large lists, and composes the home action center from a focused component.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, Testing Library, FastAPI, Pydantic, SQLite, Python unittest.

## Global Constraints

- The application remains local-only on `127.0.0.1`.
- Mutating frontend requests must include `X-Requested-With: SemixCRM` through `apiRequest`.
- Existing persisted data and API response fields remain backward compatible.
- New UI follows `design-system/semix-crm/MASTER.md`: premium dark desktop dashboard, Inter, Lucide, visible focus, subtle motion.
- No automatic external messages and no destructive backup restore in this release.
- Every behavior change follows red-green-refactor and receives an automated regression test.

---

### Task 1: Safe frontend transport and confirmed Freelance regression

**Files:**
- Modify: `src/api.ts`
- Modify: `src/pages/FreelancePage.tsx`
- Modify: `src/pages/FreelancePage.test.tsx`

**Interfaces:**
- Consumes: `apiRequest<T>(path, options)` and backend safety contract.
- Produces: all Freelance reads and mutations through `apiRequest`, including `checkNow()` and `openAuth()`.

- [ ] Add failing tests that click “Проверить сейчас” and “Войти” and assert both POST calls contain `X-Requested-With: SemixCRM`.
- [ ] Run `npm run test:frontend -- src/pages/FreelancePage.test.tsx` and confirm the two header assertions fail.
- [ ] Replace raw page-level transport with `apiRequest`; keep `runAction` responsible for busy/success/error state, not JSON parsing.
- [ ] Run the focused test and the full frontend suite; confirm success.
- [ ] Commit as `fix: unify freelance API actions`.

### Task 2: Dashboard aggregation API

**Files:**
- Create: `backend/dashboard.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_dashboard.py`

**Interfaces:**
- Consumes: `database.list_clients`, `database.get_schedule`, `database.list_freelance_orders`, `database.list_source_statuses`, `jobs.storage.list_jobs`, `jobs.storage.list_job_source_statuses`.
- Produces: `build_dashboard(now: datetime | None = None, limit: int = 5) -> dict[str, Any]` and `GET /api/dashboard`.

- [ ] Add failing unit tests asserting counters, maximum five entries per queue, descending client/job relevance, current-week unfinished tasks, and stale/error source-health labels.
- [ ] Run `backend/.venv/Scripts/python.exe -m unittest backend.tests.test_dashboard -v` and confirm import/route failures.
- [ ] Implement a pure bounded aggregator in `backend/dashboard.py`; do not call external services.
- [ ] Add `GET /api/dashboard` to `backend/main.py` with `limit` constrained to `1..20`.
- [ ] Run focused and full backend suites; confirm success.
- [ ] Commit as `feat: add daily action dashboard API`.

### Task 3: Today action center and durable navigation

**Files:**
- Create: `src/components/ActionCenter.tsx`
- Create: `src/components/ActionCenter.test.tsx`
- Modify: `src/App.tsx`
- Modify: `src/App.test.tsx`
- Modify: `src/styles.css`
- Modify: `src/premium-dark.css`

**Interfaces:**
- Consumes: `GET /api/dashboard`, `SectionId`, and `onOpen(section)`.
- Produces: typed `DashboardPayload`, retryable action queues, hash navigation, profile-to-settings navigation.

- [ ] Add failing tests for dashboard success/error/retry, direct queue navigation, initial `#clients`, browser `hashchange`, and profile button navigation.
- [ ] Run the focused Vitest files and confirm expected failures.
- [ ] Build `ActionCenter` with compact metrics, four bounded queues, source health, loading skeleton, empty states, and retry.
- [ ] Make section hashes the source of navigation state, handle Back/Forward, hide global search outside Home, add a skip link, and route the profile button to Settings with `#profile` focus intent.
- [ ] Add premium dark/light styles with stable hover states, visible focus, and common-desktop wrapping.
- [ ] Run focused and full frontend suites; confirm success.
- [ ] Commit as `feat: add daily action center`.

### Task 4: Progressive rendering for large datasets

**Files:**
- Create: `src/components/ProgressiveListFooter.tsx`
- Create: `src/components/ProgressiveListFooter.test.tsx`
- Modify: `src/pages/ClientsPage.tsx`
- Modify: `src/pages/ClientsPage.test.tsx`
- Modify: `src/pages/JobsPage.tsx`
- Modify: `src/pages/JobsPage.test.tsx`
- Modify: `src/pages/FreelancePage.tsx`
- Modify: `src/pages/FreelancePage.test.tsx`
- Modify: `src/styles.css`
- Modify: `src/premium-dark.css`

**Interfaces:**
- Produces: `ProgressiveListFooter({ shown, total, step, onMore, onAll })` and bounded page rendering with initial limits clients=60, jobs=50, freelance=50.

- [ ] Add a failing component test for count text, “Показать ещё”, “Показать все”, and hidden footer when complete.
- [ ] Add page tests proving rows beyond the initial limit are not mounted and a filter change resets the limit.
- [ ] Run focused tests and confirm failures caused by unbounded rendering.
- [ ] Implement the reusable footer and bounded `visibleItems` slices in all three pages, including archives where applicable.
- [ ] Add accessible compact styles and run focused/full frontend tests.
- [ ] Commit as `perf: progressively render CRM lists`.

### Task 5: Editable AI working profile

**Files:**
- Modify: `src/pages/SettingsPage.tsx`
- Modify: `src/pages/SettingsPage.test.tsx`
- Modify: `src/pages/SettingsPage.css`

**Interfaces:**
- Consumes: existing `GET /api/ai/profile` and `PUT /api/ai/profile` fields `name`, `role`, `stack`, `portfolio_url`, `price_from`, `cases`.
- Produces: labeled profile form with independent busy/error/success state and `id="profile"` focus target.

- [ ] Add failing tests for profile loading, editing and saved request body, plus API failure feedback.
- [ ] Run the focused settings tests and confirm missing form failures.
- [ ] Load AI settings and profile concurrently, render a dedicated profile panel, validate required name/role fields, and save through `apiRequest`.
- [ ] Style the panel consistently and run focused/full frontend tests.
- [ ] Commit as `feat: add editable AI working profile`.

### Task 6: Consistent local database backups

**Files:**
- Create: `backend/backups.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_backups.py`
- Modify: `src/pages/SettingsPage.tsx`
- Modify: `src/pages/SettingsPage.test.tsx`
- Modify: `src/pages/SettingsPage.css`

**Interfaces:**
- Produces: `create_backup()`, `list_backups()`, `resolve_backup(filename)`, `POST /api/backups`, `GET /api/backups`, and `GET /api/backups/{filename}`.

- [ ] Add failing backend tests for SQLite-consistent creation, metadata ordering, generated names, missing files, and path traversal rejection.
- [ ] Run `backend/.venv/Scripts/python.exe -m unittest backend.tests.test_backups -v` and confirm missing module/route failures.
- [ ] Implement backups with `sqlite3.Connection.backup`, fixed backup directory, `.sqlite3` suffix and strict filename regex; expose download via `FileResponse`.
- [ ] Add failing frontend tests for listing and creating a backup, then implement the Settings data panel with download links and feedback.
- [ ] Run focused and full test suites.
- [ ] Commit as `feat: add safe database backups`.

### Task 7: Release hardening and live verification

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Modify: `README.md`
- Create: `.github/workflows/ci.yml`
- Modify only if verification finds a defect: files covered by the failing regression.

**Interfaces:**
- Produces: reproducible frontend scripts, CI verification, updated operating/backup documentation.

- [ ] Add `test`, `typecheck`, and `check` scripts; move Vite/plugin-react to dev dependencies and replace `latest` declarations with installed compatible versions.
- [ ] Run `npm install`, `npm audit`, and `npm outdated`; apply compatible security updates without changing application behavior.
- [ ] Add Windows/Linux-neutral GitHub CI for frontend tests/build and backend unittest with requirements installation.
- [ ] Update README with action center, profile, backups, local-only warning, source-health meaning, and the correct `backend/.venv` test command.
- [ ] Run backend tests, frontend tests, build, `pip check`, `npm audit`, Python compile, SQLite integrity check, and `git diff --check`.
- [ ] Inspect 1024px and 1440px desktop layouts, both themes, keyboard focus, hash navigation, progressive lists, profile save, backup creation/download, and Freelance safe actions in the in-app browser.
- [ ] Commit as `chore: harden Semix CRM release`, push `main`, and verify local HEAD equals `origin/main`.
