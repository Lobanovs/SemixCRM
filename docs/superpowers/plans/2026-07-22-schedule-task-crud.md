# Schedule Task CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add complete task create, read, update, completion-toggle, and delete interactions to the weekly schedule frontend.

**Architecture:** Keep the existing FastAPI and SQLite CRUD routes as the source of truth. Refactor the React schedule page to use one create/edit modal, separate completion and edit controls, and day-level creation triggers; reload schedule data after each mutation.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, FastAPI, SQLite, Python unittest, CSS.

## Global Constraints

- Clicking a day header or empty task area creates a task for that date.
- Clicking a task opens editing; clicking its checkbox only toggles completion.
- Editing supports title, date, time, and kind.
- Delete requires explicit confirmation and keeps the modal open on API failure.
- Existing API routes and database schema remain compatible.
- Desktop is the primary layout; light/dark themes and keyboard accessibility must remain usable.
- Every project change is committed and pushed to `origin/main`.

---

### Task 1: Lock backend CRUD behavior with regression tests

**Files:**
- Modify: `backend/tests/test_schedule.py`
- Modify: `backend/tests/test_schedule_api.py`

**Interfaces:**
- Consumes: `create_schedule_task`, `update_schedule_task`, `delete_schedule_task`.
- Produces: proven persistence and HTTP behavior for task CRUD.

- [ ] **Step 1: Add failing database/API coverage**

Add a database test that creates a task, updates all editable fields, deletes it, and verifies the week is empty. Add API tests that verify `PUT /api/schedule/tasks/{id}`, `DELETE /api/schedule/tasks/{id}`, and `404` for a missing task.

```python
task = database.create_schedule_task("2026-07-20", "Черновик")
updated = database.update_schedule_task(int(task["id"]), "Готовая задача", "2026-07-21", "14:30", "meeting", True)
self.assertEqual("Готовая задача", updated["title"])
self.assertTrue(database.delete_schedule_task(int(task["id"])))
self.assertEqual([], database.get_schedule("2026-07-20")["tasks"])
```

- [ ] **Step 2: Run focused tests and verify the new tests detect any missing behavior**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_schedule backend.tests.test_schedule_api -v`

Expected: new CRUD assertions pass against the existing backend; any uncovered API mismatch fails before frontend work.

- [ ] **Step 3: Make only backend fixes required by the tests**

Keep the existing route signatures. A successful delete returns `{"deleted": true}`; missing update/delete returns HTTP 404.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit and push**

```powershell
git add backend/tests/test_schedule.py backend/tests/test_schedule_api.py backend/main.py backend/database.py
git commit -m "test: cover schedule task CRUD"
git push origin main
```

### Task 2: Add day creation and shared create/edit modal

**Files:**
- Create: `src/pages/SchedulePage.test.tsx`
- Modify: `src/pages/SchedulePage.tsx`

**Interfaces:**
- Produces: `TaskModal({ defaultDate, task, onClose, onSaved, onDeleted })`.
- Produces: `WeekColumn` callbacks `onCreate(date)`, `onEdit(task)`, and `onToggle(task)`.

- [ ] **Step 1: Write failing frontend tests for day click and creation**

Mock `GET /api/schedule` and `POST /api/schedule/tasks`. Assert that clicking `Добавить задачу на 22.07` opens a dialog with date `2026-07-22`, and submitting sends:

```typescript
expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
  title: 'Новая задача',
  task_date: '2026-07-22',
  task_time: '13:00',
  kind: 'task',
})
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm.cmd run test:frontend -- src/pages/SchedulePage.test.tsx`

Expected: the day create control/dialog behavior is missing.

- [ ] **Step 3: Implement selected-day creation and modal modes**

Add `editingTask: Task | null` plus a modal date state. `openCreate(date)` selects the date and opens an empty modal; `openEdit(task)` opens populated edit mode. Creation uses POST, edit uses PUT with `title`, `task_date`, `task_time`, and `kind`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: creation tests pass.

- [ ] **Step 5: Commit and push**

```powershell
git add src/pages/SchedulePage.tsx src/pages/SchedulePage.test.tsx
git commit -m "feat: create and edit daily schedule tasks"
git push origin main
```

### Task 3: Add independent completion, confirmed deletion, and polished UI

**Files:**
- Modify: `src/pages/SchedulePage.test.tsx`
- Modify: `src/pages/SchedulePage.tsx`
- Modify: `src/styles.css`

**Interfaces:**
- Completion PUT body: `{ done: boolean }`.
- Delete endpoint: `DELETE /api/schedule/tasks/{id}`.

- [ ] **Step 1: Write failing edit, completion, delete, and error tests**

Assert that task-card click opens populated edit mode; checkbox click sends only `{ done: true }`; first delete click shows confirmation; second sends DELETE; failed PUT/DELETE renders a modal `role="alert"` and keeps the dialog open.

- [ ] **Step 2: Run tests and verify RED**

Run: `npm.cmd run test:frontend -- src/pages/SchedulePage.test.tsx`

Expected: independent controls, confirmation, and modal error behavior are absent.

- [ ] **Step 3: Implement minimal behavior and CSS**

Use `SquarePen` for edit, `Trash2` for delete, `Plus` for day creation, semantic button labels, visible focus styles, at least 40 px interactive targets, and existing light/dark theme colors. Keep task title and time readable in narrow columns.

- [ ] **Step 4: Run all automated verification**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm.cmd run test:frontend
npm.cmd run build
```

Expected: zero test failures and build exit 0.

- [ ] **Step 5: Verify the live frontend**

Against `http://127.0.0.1:5173/`, create a temporary task by clicking a day, edit its fields, toggle completion, delete it with confirmation, verify it disappears, and confirm no horizontal overflow in light and dark themes.

- [ ] **Step 6: Mark this plan complete, commit, and push**

```powershell
git add src/pages/SchedulePage.tsx src/pages/SchedulePage.test.tsx src/styles.css docs/superpowers/plans/2026-07-22-schedule-task-crud.md
git commit -m "feat: complete schedule task CRUD"
git push origin main
```
