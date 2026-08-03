# AI Week Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a review-first OpenCode Go weekly planner to the Schedule page that generates structured tasks and safely applies selected items.

**Architecture:** A new pure planning service owns prompts and response validation. FastAPI exposes guarded generate/apply endpoints; database batch insertion provides all-or-nothing persistence and duplicate skipping. A focused React modal owns the brief, preview, selection, regeneration, and apply flow.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLite, unittest, React 19, TypeScript, Vitest, Testing Library, CSS.

## Global Constraints

- Use the existing OpenCode Go settings and `AiClient.complete_json`; do not add another API key or provider.
- Generation never writes schedule data.
- Applying never deletes or overwrites existing tasks.
- Apply validates every task and inserts the batch atomically.
- Exact same-date/title duplicates are skipped.
- Current-week plans cannot contain past dates.
- Weekend tasks are rejected unless `include_weekend` is true.
- Keep existing light and premium-black themes and use Lucide icons only.
- Commit and push every completed project change to `origin/main`.

---

### Task 1: Planning service and validation

**Files:**
- Create: `backend/ai/schedule.py`
- Create: `backend/tests/test_ai_schedule.py`

**Interfaces:**
- Consumes: `AiClient.complete_json(system, user, temperature, max_tokens, validate=...)` and trusted `schedule: dict[str, Any]`.
- Produces: `generate_week_plan(*, week_start: str, objective: str, intensity: str, include_weekend: bool, schedule: dict[str, Any], ai_client: AiClient | None = None, today: date | None = None) -> dict[str, Any]`.

- [ ] **Step 1: Write failing planner tests**

Cover a valid normalized plan, prompt inclusion of unfinished goals/existing tasks, same-plan duplicate removal, date outside week, past-day rejection, weekend rejection, invalid time, and unsupported task kind. Use a fake client whose `complete_json` invokes the supplied validator on a real payload.

```python
result = generate_week_plan(
    week_start="2026-08-03",
    objective="Закончить лендинг",
    intensity="balanced",
    include_weekend=False,
    schedule=SCHEDULE,
    ai_client=FakeAiClient(PAYLOAD),
    today=date(2026, 8, 3),
)
self.assertEqual("2026-08-09", result["week_end"])
self.assertEqual("Собрать список оставшихся блоков", result["tasks"][0]["title"])
```

- [ ] **Step 2: Verify RED**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_schedule -v`

Expected: FAIL because `backend.ai.schedule` does not exist.

- [ ] **Step 3: Implement the minimal service**

Add constants for intensity limits, strict prompt/schema text, `_normalize_task`, `_validate_payload`, and `generate_week_plan`. Return stable IDs `ai-1`, `ai-2`, etc. Sort by date, empty-time-last, then original order. Limit normalized plans to 20 tasks.

- [ ] **Step 4: Verify GREEN**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_schedule -v`

Expected: all planner tests PASS.

- [ ] **Step 5: Commit and push**

```powershell
git add backend/ai/schedule.py backend/tests/test_ai_schedule.py
git commit -m "feat: add ai week planning service"
git push origin main
```

### Task 2: Atomic apply storage and FastAPI endpoints

**Files:**
- Modify: `backend/database.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_ai_schedule_api.py`

**Interfaces:**
- Consumes: `generate_week_plan(...)` and selected draft tasks.
- Produces: `apply_schedule_task_batch(week_start: str, tasks: list[dict[str, Any]], focus: str) -> dict[str, Any]`, `POST /api/ai/schedule/plan`, and `POST /api/ai/schedule/plan/apply`.

- [ ] **Step 1: Write failing API/storage tests**

Test that generation receives server-loaded schedule context and requires the powerful-action header. Test disabled AI → 503 and provider error → 502. Test apply inserts selected tasks, skips exact duplicates, preserves goals/summary, persists focus, and returns a refreshed schedule. Test one invalid item leaves the database unchanged.

```python
response = self.client.post(
    "/api/ai/schedule/plan/apply",
    headers={"X-Requested-With": "SemixCRM"},
    json={"week_start": "2026-08-03", "focus": "Запуск", "tasks": TASKS},
)
self.assertEqual(200, response.status_code)
self.assertEqual(1, response.json()["created_count"])
self.assertEqual(1, response.json()["skipped_count"])
```

- [ ] **Step 2: Verify RED**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_schedule_api -v`

Expected: FAIL because the routes and batch function do not exist.

- [ ] **Step 3: Implement atomic batch storage**

Normalize all tasks before opening the transaction. Inside one connection, load existing same-week `(task_date, casefold(title))` keys, insert non-duplicates, update `schedule_weeks.focus` while preserving `summary` and `goals_json`, then return created tasks and counts. Let any validation/SQL exception roll back the whole context manager.

- [ ] **Step 4: Implement Pydantic contracts and endpoints**

Add `AiSchedulePlanRequest`, `AiScheduleDraftTask`, and `AiScheduleApplyRequest`. Both endpoints use `Depends(guard_powerful_action)`. Map `AiDisabledError` to 503, `AiError` to 502, and `ValueError` to 422.

- [ ] **Step 5: Verify GREEN and regressions**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_schedule_api backend.tests.test_schedule backend.tests.test_schedule_api -v`

Expected: all selected tests PASS.

- [ ] **Step 6: Commit and push**

```powershell
git add backend/database.py backend/main.py backend/tests/test_ai_schedule_api.py
git commit -m "feat: expose ai schedule planning api"
git push origin main
```

### Task 3: Planner modal behavior

**Files:**
- Create: `src/pages/AiWeekPlannerModal.tsx`
- Modify: `src/pages/SchedulePage.tsx`
- Modify: `src/pages/SchedulePage.test.tsx`

**Interfaces:**
- Consumes: `POST /api/ai/schedule/plan`, `POST /api/ai/schedule/plan/apply`, selected week data and unfinished goals.
- Produces: `AiWeekPlannerModal({ weekStart, weekEnd, goals, onClose, onApplied })` and toolbar action `Составить неделю с ИИ`.

- [ ] **Step 1: Extend the fetch fixture and write the failing UI test**

The test opens the modal, enters the objective, selects balanced load, generates a preview, unchecks one suggestion, and applies the rest. Assert the guarded generate request and the apply request body.

```tsx
await user.click(await screen.findByRole('button', { name: 'Составить неделю с ИИ' }))
const dialog = screen.getByRole('dialog', { name: 'ИИ-планировщик недели' })
await user.type(within(dialog).getByLabelText('Главный результат недели'), 'Закончить лендинг')
await user.click(within(dialog).getByRole('button', { name: 'Составить черновик' }))
expect(await within(dialog).findByText('Собрать список оставшихся блоков')).toBeVisible()
```

Also test provider errors stay in the dialog with `role="alert"` and regeneration does not save anything.

- [ ] **Step 2: Verify RED**

Run: `npm.cmd run test:frontend -- src/pages/SchedulePage.test.tsx`

Expected: FAIL because the AI planner button/modal does not exist.

- [ ] **Step 3: Implement the modal**

Use controlled fields and local state. Generate via the shared `src/api.ts` client so `X-Requested-With: SemixCRM` is present. Render two phases, group tasks by date, use native checked checkboxes with stable AI task IDs, disable actions during requests, and announce errors.

- [ ] **Step 4: Connect SchedulePage**

Add `showAiPlanner` state, the sparkle toolbar button, and `onApplied` that closes the modal, reloads the selected week, and displays `Добавлено N задач` plus skipped count when non-zero.

- [ ] **Step 5: Verify GREEN**

Run: `npm.cmd run test:frontend -- src/pages/SchedulePage.test.tsx`

Expected: all Schedule page tests PASS.

- [ ] **Step 6: Commit and push**

```powershell
git add src/pages/AiWeekPlannerModal.tsx src/pages/SchedulePage.tsx src/pages/SchedulePage.test.tsx
git commit -m "feat: add ai planner to weekly schedule"
git push origin main
```

### Task 4: Visual system, guide, documentation, and end-to-end verification

**Files:**
- Create: `src/pages/AiWeekPlannerModal.css`
- Modify: `src/premium-dark.css`
- Modify: `src/guides.ts`
- Modify: `src/guides.test.ts`
- Modify: `README.md`

**Interfaces:**
- Consumes: modal class names and existing Semix tokens.
- Produces: accessible desktop modal in both themes and documented workflow.

- [ ] **Step 1: Write the failing guide test**

Assert `SCHEDULE_GUIDE` contains a step targeting `[data-guide="schedule-ai-plan"]` whose text explains generation, review, and explicit apply.

- [ ] **Step 2: Verify RED**

Run: `npm.cmd run test:frontend -- src/guides.test.ts`

Expected: FAIL because the AI planner guide step is absent.

- [ ] **Step 3: Add modal styles and guide content**

Use a maximum 900px desktop dialog, fixed header/footer, scrollable content, compact 8px rhythm, Lucide icons, visible focus, 180ms state transitions, loading feedback, and `role="alert"`. Add premium-black overrides using existing `--premium-*` tokens and preserve reduced-motion behavior.

- [ ] **Step 4: Update README**

Document that Schedule can generate a reviewable OpenCode Go weekly draft, that existing tasks are preserved, and that applying selected tasks is explicit.

- [ ] **Step 5: Run full automated verification**

Run: `npm.cmd run test:frontend`

Expected: all frontend tests PASS.

Run: `backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v`

Expected: all backend tests PASS.

Run: `npm.cmd run build`

Expected: TypeScript and Vite build succeed.

- [ ] **Step 6: Browser QA**

At `http://127.0.0.1:5173/`, open Schedule, generate a real plan with the configured OpenCode Go model, review the draft, exclude one item, apply the remainder, confirm the week refreshes, then delete only the QA-created tasks. Verify light/dark presentation and browser console errors.

- [ ] **Step 7: Commit and push**

```powershell
git add src/pages/AiWeekPlannerModal.css src/premium-dark.css src/guides.ts src/guides.test.ts README.md
git commit -m "docs: finish ai week planner experience"
git push origin main
```
