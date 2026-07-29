# Useful Things Categories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в «Полезные вещи» категории со вкладками и полноценное хранение
промптов без обязательной ссылки.

**Architecture:** Существующий SQLite/FastAPI контракт расширяется полем `category`,
а старая таблица безопасно перестраивается для поддержки пустого URL у промптов.
React продолжает загружать каталог одним запросом, а вкладки, счётчики и поиск
вычисляются локально.

**Tech Stack:** Python 3.13, SQLite, FastAPI, Pydantic, React, TypeScript, Lucide,
unittest, Vitest, Testing Library.

## Global Constraints

- Категории API: `prompt`, `website`, `shop`, `article`, `other`.
- Отсутствующая категория означает `website` для обратной совместимости.
- Промпт требует непустое описание до 5000 символов и не требует URL.
- Остальные категории требуют уникальный нормализованный HTTP(S) URL и допускают
  описание до 1000 символов.
- Старые строки мигрируют без потери id, дат и содержимого в `website`.
- Frontend использует только Lucide-иконки, действия не меньше 44×44 px,
  видимые labels/focus и `aria-pressed` для вкладок.
- Все изменяющие запросы сохраняют `X-Requested-With: SemixCRM`.

---

### Task 1: SQLite migration and category-aware API

**Files:**
- Modify: `backend/tests/test_useful_links.py`
- Modify: `backend/database.py`
- Modify: `backend/main.py`

**Interfaces:**
- Produces: `USEFUL_LINK_CATEGORIES`.
- Produces: `create_useful_link(title, url="", description="", category="website")`.
- Produces: `update_useful_link(link_id, title=None, url=None, description=None, category=None)`.
- Produces: serialized `category` and category counts under `stats.categories`.

- [x] **Step 1: Write database RED tests**

Add tests that create two prompts with empty URLs, reject an empty prompt body,
reject an unknown category, keep normal URL uniqueness, and rebuild a manually
created legacy table while preserving its row as `website`.

- [x] **Step 2: Verify database RED**

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.tests.test_useful_links.UsefulLinksDatabaseTests
```

Expected: failures because `category` is missing and prompt URLs are rejected.

- [x] **Step 3: Implement schema migration and validation**

Create the new table shape:

```sql
CREATE TABLE useful_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'website',
  url TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_useful_links_url
ON useful_links(url) WHERE url <> '';
```

If `PRAGMA table_info(useful_links)` has no `category` or reports `url` as
`NOT NULL` without the new default, rename it, create the new shape, copy rows as
`website`, and drop the legacy table.

Update normalization, serialization and CRUD signatures. Derive category counts
from serialized rows in `list_useful_links`.

- [x] **Step 4: Verify database GREEN**

Run the Step 2 command. Expected: all database tests pass.

- [x] **Step 5: Write API RED tests**

Add API cases for creating a prompt with `url: ""`, defaulting an old request to
`website`, changing category through PUT and returning `422` for an invalid category
or a prompt without text.

- [x] **Step 6: Verify API RED**

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.tests.test_useful_links.UsefulLinksApiTests
```

Expected: Pydantic or response failures because category-aware requests are absent.

- [x] **Step 7: Implement API models**

Add `category: Literal[...] = "website"` to creation, optional category and optional
empty URL to update, pass all fields by keyword to database functions and keep
existing 409/422/404 mappings.

- [x] **Step 8: Verify Task 1**

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.tests.test_useful_links
```

Expected: all useful catalog backend tests pass.

---

### Task 2: Category tabs and prompt interaction

**Files:**
- Modify: `src/pages/UsefulThingsPage.test.tsx`
- Modify: `src/pages/UsefulThingsPage.tsx`
- Modify: `src/pages/UsefulThingsPage.css`

**Interfaces:**
- Consumes: Task 1 category-aware payload.
- Produces: tabs `all`, `prompt`, `website`, `shop`, `article`, `other`.
- Produces: prompt card copy action and category-aware shared form.

- [x] **Step 1: Write tabs RED tests**

Expand the fixture with prompt, shop and article entries. Assert that every tab has
its count, `aria-pressed` changes on click, category filtering is local, and search
applies inside the active category without another fetch.

- [x] **Step 2: Verify tabs RED**

```powershell
npm.cmd run test:frontend -- --run src/pages/UsefulThingsPage.test.tsx
```

Expected: missing category buttons and category fields.

- [x] **Step 3: Implement category model and derived filters**

Add category config with Russian labels and Lucide icons. Store only active category
and query as state; derive counts and displayed records with `useMemo`. Render a
horizontal tab list with `aria-pressed`, badge counts and a distinct active state.

- [x] **Step 4: Write prompt form RED test**

Select «Промпты», open the form, assert URL is absent, fill «Текст промпта», save,
and verify POST body:

```json
{
  "title": "Аудит лендинга",
  "category": "prompt",
  "url": "",
  "description": "Проанализируй лендинг..."
}
```

- [x] **Step 5: Implement category-aware form and cards**

Render a category selector. For prompts require description up to 5000 and hide URL;
for other types require URL and limit description to 1000. Show category badges and
use «Открыть» for links, «Копировать» for prompts. Keep edit/delete behavior generic.

- [x] **Step 6: Write and implement copy behavior**

Mock `navigator.clipboard.writeText`, click «Копировать Аудит лендинга», assert the
full prompt is copied and a `role="status"` success message appears. On rejection,
show an accessible error.

- [x] **Step 7: Style and verify Task 2**

Add dense Semix tabs with counts, category colors/icons, 44 px interactions, light
and dark themes, horizontal overflow only inside the tab row, and reduced motion.

```powershell
npm.cmd run test:frontend -- --run src/pages/UsefulThingsPage.test.tsx src/App.test.tsx
```

Expected: all page and application navigation tests pass.

---

### Task 3: Documentation, live verification and delivery

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-29-useful-things-categories.md`

**Interfaces:**
- Consumes: completed backend and frontend.
- Produces: verified and published `main`.

- [x] **Step 1: Update README**

Document all categories, prompt behavior, filters, migration and copy action.

- [x] **Step 2: Restart backend and verify migration**

Restart only the verified Semix CRM uvicorn process on port 8000, confirm health and
that existing useful records remain available with `category: "website"`.

- [x] **Step 3: Run full verification**

```powershell
npm.cmd run test:frontend
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests
npm.cmd run build
git diff --check
```

Expected: all tests pass, build succeeds and diff check is clean.

- [x] **Step 4: Verify live UI CRUD**

Through the browser create a temporary prompt and article, switch tabs, search,
copy and edit the prompt, then delete both temporary records. Confirm the catalog
returns to its original contents.

- [x] **Step 5: Commit and push**

Commit backend, frontend, tests, README and this completed plan, push `main`, then
verify local HEAD equals `refs/heads/main` on `origin` and the worktree is clean.
