# Useful Things Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в Semix CRM полноценный CRUD-каталог полезных рабочих сайтов.

**Architecture:** Новая SQLite-таблица и функции `backend.database` формируют единый
источник данных. FastAPI публикует небольшой REST-контракт, а отдельная React-страница
загружает каталог, фильтрует его локально и синхронизирует CRUD-операции через API.

**Tech Stack:** Python 3.13, SQLite, FastAPI, Pydantic, React, TypeScript, Lucide,
unittest, Vitest, Testing Library.

## Global Constraints

- Поля: `title` 1–120, `url` 1–2048, `description` 0–1000 символов.
- URL без схемы получает `https://`; разрешены только HTTP(S) и непустой hostname.
- Одинаковый нормализованный URL нельзя сохранить дважды.
- Изменяющие API-запросы требуют `X-Requested-With: SemixCRM`.
- Интерфейс рассчитан прежде всего на desktop, но не создаёт горизонтальный скролл.
- Все поля имеют видимые label; ошибки доступны через `role="alert"`.
- Иконки только Lucide, анимации 150–300 ms и видимые focus-состояния.

---

### Task 1: SQLite и REST API

**Files:**
- Create: `backend/tests/test_useful_links.py`
- Modify: `backend/database.py`
- Modify: `backend/main.py`

**Interfaces:**
- Produces: `list_useful_links() -> dict[str, Any]`.
- Produces: `create_useful_link(title, url, description) -> dict[str, Any]`.
- Produces: `update_useful_link(link_id, title=None, url=None, description=None)`.
- Produces: `delete_useful_link(link_id) -> bool`.
- Produces: `GET/POST /api/useful-links`, `PUT/DELETE /api/useful-links/{link_id}`.

- [x] **Step 1: Write database RED tests**

Create tests that initialize a temporary database, create `figma.com`, assert storage
as `https://figma.com`, update all three fields, list newest first, delete the row, and
receive `False` on a repeated delete. Add validation cases for unsupported protocols,
empty hostname and duplicate normalized URL.

- [x] **Step 2: Verify database RED**

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.tests.test_useful_links.UsefulLinksDatabaseTests
```

Expected: import or attribute failures because the table/functions do not exist.

- [x] **Step 3: Implement the SQLite contract**

Add `useful_links` to `init_db`, URL normalization through `urllib.parse.urlsplit`,
row serialization, sorted listing and the four database operations. Convert SQLite
uniqueness failures to `ValueError("Этот сайт уже добавлен")`.

- [x] **Step 4: Verify database GREEN**

Run the Task 1 Step 2 command. Expected: all database tests pass.

- [x] **Step 5: Write API RED tests**

Add a `TestClient` group that checks HTTP 201 creation, GET listing, PUT update,
DELETE removal, HTTP 404 for an absent id, HTTP 422 for an invalid URL, HTTP 409 for
a duplicate and HTTP 403 for mutations without the custom header.

- [x] **Step 6: Verify API RED**

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.tests.test_useful_links.UsefulLinksApiTests
```

Expected: 404 responses because routes are absent.

- [x] **Step 7: Implement the FastAPI routes**

Add Pydantic create/update models, import the database functions, map missing resources
to 404, URL validation to 422 and duplicate errors to 409. Apply
`Depends(guard_powerful_action)` to POST, PUT and DELETE.

- [x] **Step 8: Verify Task 1**

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.tests.test_useful_links
```

Expected: all useful-link tests pass.

---

### Task 2: React catalog and application navigation

**Files:**
- Create: `src/pages/UsefulThingsPage.tsx`
- Create: `src/pages/UsefulThingsPage.css`
- Create: `src/pages/UsefulThingsPage.test.tsx`
- Modify: `src/App.tsx`
- Modify: `src/App.test.tsx`

**Interfaces:**
- Consumes: Task 1 REST API.
- Produces: `UsefulThingsPage` default React component.
- Produces: new stable section id `useful`.

- [x] **Step 1: Write page RED tests**

Mock `fetch` and assert:

- loaded cards display title/domain/description;
- typing in search filters without a request;
- the add form POSTs title, URL and description with `X-Requested-With`;
- the edit form PUTs the selected id and refreshes the card;
- delete requires confirmation before issuing DELETE;
- failed requests appear as an accessible alert.

- [x] **Step 2: Verify page RED**

```powershell
npm.cmd run test:frontend -- --run src/pages/UsefulThingsPage.test.tsx
```

Expected: import failure because the page does not exist.

- [x] **Step 3: Implement the React behavior**

Use controlled inputs and `apiRequest`, keep server data in `items`, derive filtered
items with `useMemo`, update the local list after successful mutations, and keep
modal/open/delete/busy/feedback state explicit. External links must use
`target="_blank"` and `rel="noreferrer"`.

- [x] **Step 4: Implement the page styling**

Build a dense blue-accent directory with a two-to-three-column card grid, visible
labels, 44 px actions, helpful loading/empty/no-results states, a 150–200 ms hover
transition, reduced-motion handling and explicit dark-theme overrides.

- [x] **Step 5: Verify page GREEN**

Run the Task 2 Step 2 command. Expected: all page tests pass.

- [x] **Step 6: Write navigation RED**

Extend `src/App.test.tsx` to click «Полезные вещи» and expect the new level-one
heading. The test must fail while `SectionId`, `menuItems` and rendering are unchanged.

- [x] **Step 7: Wire navigation and quick access**

Import `Bookmark` and `UsefulThingsPage`, add `useful` to `SectionId`, add a feature
entry and menu item through the shared `features` list, render the page in the active
section chain, and renumber the settings guide step.

- [x] **Step 8: Verify Task 2**

```powershell
npm.cmd run test:frontend -- --run src/pages/UsefulThingsPage.test.tsx src/App.test.tsx
```

Expected: page and navigation tests pass.

---

### Task 3: Documentation, live verification and delivery

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-29-useful-things.md`

**Interfaces:**
- Consumes: completed API and page.
- Produces: documented, verified and pushed `main`.

- [x] **Step 1: Update README**

Add «Полезные вещи» to the capability table and document its stored fields, CRUD,
URL normalization and SQLite persistence.

- [x] **Step 2: Restart local backend**

Stop only the process verified as Semix CRM uvicorn on port 8000, start the updated
backend hidden, and confirm `/api/health`.

- [x] **Step 3: Run full verification**

```powershell
npm.cmd run test:frontend
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests
npm.cmd run build
git diff --check
```

Expected: all tests pass, production build succeeds and diff check is clean.

- [x] **Step 4: Verify live CRUD**

Create a temporary useful link through the live API, update it, list it and delete it.
Confirm the final list no longer includes the temporary row.

- [ ] **Step 5: Commit and push**

```powershell
git add backend/database.py backend/main.py backend/tests/test_useful_links.py `
  src/App.tsx src/App.test.tsx src/pages/UsefulThingsPage.tsx `
  src/pages/UsefulThingsPage.css src/pages/UsefulThingsPage.test.tsx README.md `
  docs/superpowers/plans/2026-07-29-useful-things.md
git commit -m "feat: add useful things catalog"
git push origin main
```
