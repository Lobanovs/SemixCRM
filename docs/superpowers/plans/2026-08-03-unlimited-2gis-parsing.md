# Unlimited 2GIS Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a true user-facing “all companies” mode that lets parser-2gis traverse a complete 2GIS result set without SemixCRM’s old 50/200-record and ten-minute ceilings.

**Architecture:** Use `limit = 0` as the SemixCRM API/database sentinel for unlimited 2GIS parsing. Translate that sentinel only at the upstream boundary into a very large positive `parser.max_records` value, because parser-2gis 1.2.1 already paginates until no next page exists but validates its stop counter as positive. Keep Yandex Maps at its existing safe 50-record maximum when all-mode is used.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLite, unittest, React, TypeScript, Vitest, Testing Library, CSS, parser-2gis 1.2.1.

## Global Constraints

- Work directly on `main`; commit and push every completed project change to `origin/main`.
- `limit = 0` means all available 2GIS companies; every positive integer means an explicit limit.
- Existing saved positive limits must remain unchanged.
- Start-page behavior must continue to work in both modes.
- Yandex Maps remains limited to 50 records per niche when 2GIS all-mode is selected.
- Desktop layout is primary, with no horizontal overflow on narrower screens.
- Use existing Lucide icons and support light, dark, and premium-dark themes.

---

### Task 1: Backend unlimited contract and runtime

**Files:**
- Modify: `backend/tests/test_parser_start_page.py`
- Modify: `backend/main.py:108-121,778-792`
- Modify: `backend/database.py:36-42,1367-1396`
- Modify: `backend/parser.py:82-268`

**Interfaces:**
- Consumes: existing `collect_2gis(city, niche, limit, on_status, start_page)` and parser settings APIs.
- Produces: `UNLIMITED_LIMIT = 0`, `UPSTREAM_UNLIMITED_MAX_RECORDS = 2_147_483_647`, `limit >= 0` API validation, unlimited-safe loading and aggregation.

- [ ] **Step 1: Write failing persistence and validation tests**

Add tests that save `limit=0`, save a positive value above 50, and instantiate both request models with `limit=0`:

```python
def test_parser_settings_persist_unlimited_and_large_limits(self) -> None:
    self.assertEqual(0, database.save_parser_settings("Новосибирск", ["стоматологии"], ["2gis"], 0)["limit"])
    self.assertEqual(275, database.save_parser_settings("Новосибирск", ["стоматологии"], ["2gis"], 275)["limit"])

def test_api_models_accept_unlimited_limit(self) -> None:
    self.assertEqual(0, main.ParseRequest(city="Новосибирск", niches=["стоматологии"], sources=["2gis"], limit=0).limit)
    self.assertEqual(0, main.ParserSettingsRequest(city="Новосибирск", niches=["стоматологии"], sources=["2gis"], limit=0).limit)
```

- [ ] **Step 2: Write failing runtime tests**

Capture the parser command and timeout for `limit=0`, write 75 fixture cards, and assert all 75 return:

```python
def test_collect_2gis_unlimited_uses_upstream_ceiling_without_global_timeout(self) -> None:
    captured = {}
    def fake_run(command, _environment, timeout):
        captured.update(command=command, timeout=timeout)
        Path(command[command.index("-o") + 1]).write_text(json.dumps([{"name": f"Клиника {i}"} for i in range(75)]), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="Готово")
    # patch runtime helpers and call collect_2gis(..., limit=0)
    self.assertEqual(parser.UPSTREAM_UNLIMITED_MAX_RECORDS, int(captured["command"][captured["command"].index("--parser.max-records") + 1]))
    self.assertIsNone(captured["timeout"])
    self.assertEqual(75, len(leads))
```

Also patch `collect_2gis` to return 75 unique cards and assert `collect_leads(..., limit=0)` retains all of them after deduplication.

- [ ] **Step 3: Run backend tests and confirm RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_parser_start_page -v
```

Expected: failures from the `ge=1` validators, database clamp, upstream command clamp, timeout, and final result slicing.

- [ ] **Step 4: Implement the backend contract**

Change both Pydantic fields to `Field(default=10, ge=0)`, persist `max(0, int(limit))`, and add parser helpers equivalent to:

```python
UNLIMITED_LIMIT = 0
UPSTREAM_UNLIMITED_MAX_RECORDS = 2_147_483_647

def _is_unlimited(limit: int) -> bool:
    return int(limit) == UNLIMITED_LIMIT

def _upstream_2gis_limit(limit: int) -> int:
    return UPSTREAM_UNLIMITED_MAX_RECORDS if _is_unlimited(limit) else max(1, int(limit))
```

Allow `_run_parser_process(..., timeout: int | None)`, use `None` for unlimited 2GIS, remove the 200-record and 600-second clamps, skip JSON/result slicing when unlimited, and use 50 as the Yandex fallback for `limit=0`.

- [ ] **Step 5: Run focused backend tests and confirm GREEN**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_parser_start_page backend.tests.test_parser2gis_runtime -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit and push backend behavior**

```powershell
git add backend/tests/test_parser_start_page.py backend/main.py backend/database.py backend/parser.py
git commit -m "feat: parse complete 2gis result sets"
git push origin main
```

### Task 2: Parser scope control on the frontend

**Files:**
- Modify: `src/pages/ClientsPage.test.tsx`
- Modify: `src/pages/parserSettings.ts`
- Modify: `src/pages/ClientsPage.tsx:199`
- Modify: `src/pages/ParserControlPanel.tsx:1-190`
- Modify: `src/styles.css:4380-4780`
- Modify: `src/premium-dark.css:700-730`

**Interfaces:**
- Consumes: backend `limit=0` sentinel and existing `ParserSettings` state.
- Produces: labelled “Все компании / Указать лимит” control and unbounded positive numeric input.

- [ ] **Step 1: Write failing all-mode page test**

Add a test that clicks “Все компании”, saves, and checks the PUT payload:

```tsx
await user.click(await screen.findByRole('button', { name: 'Все компании' }))
await user.click(screen.getByRole('button', { name: 'Сохранить настройки' }))
expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({ limit: 0 })
```

- [ ] **Step 2: Write failing custom-limit page test**

Select “Указать лимит”, replace the number with `275`, save, and assert `{ limit: 275 }` is sent unchanged.

- [ ] **Step 3: Run frontend tests and confirm RED**

Run:

```powershell
npm.cmd run test:frontend -- src/pages/ClientsPage.test.tsx
```

Expected: the scope buttons and custom limit input do not exist.

- [ ] **Step 4: Implement normalization and scope UI**

Normalize values with zero preserved and no 50 clamp:

```ts
export const normalizeParserLimit = (limit: number) => {
  if (!Number.isFinite(limit)) return 1
  const rounded = Math.round(limit)
  return rounded <= 0 ? 0 : rounded
}
```

Render a labelled button group with `aria-pressed`, set `limit=0` for all-mode, retain the last useful custom value when switching back, disable all-mode without 2GIS, and switch to finite 50 if 2GIS is removed while unlimited is active.

- [ ] **Step 5: Style all themes**

Add dense two-column segmented buttons, a compact number input, helper copy, `:hover`, `:focus-visible`, disabled, active, dark, and premium-dark states. Keep transitions at 150–200 ms and allow wrapping below the desktop width.

- [ ] **Step 6: Run focused frontend tests and confirm GREEN**

Run:

```powershell
npm.cmd run test:frontend -- src/pages/ClientsPage.test.tsx
```

Expected: all parser control tests pass.

- [ ] **Step 7: Commit and push frontend behavior**

```powershell
git add src/pages/ClientsPage.test.tsx src/pages/parserSettings.ts src/pages/ClientsPage.tsx src/pages/ParserControlPanel.tsx src/styles.css src/premium-dark.css
git commit -m "feat: add unlimited parser scope control"
git push origin main
```

### Task 3: Regression, live 2GIS proof, and handoff

**Files:**
- Modify only if verification uncovers a defect in the files from Tasks 1–2.

**Interfaces:**
- Consumes: completed backend and frontend implementation.
- Produces: test evidence, live parser evidence, remote SHA parity.

- [ ] **Step 1: Run full automated verification**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm.cmd run test:frontend
npm.cmd run build
git diff --check
```

Expected: backend and frontend suites pass, Vite production build succeeds, and `git diff --check` is empty.

- [ ] **Step 2: Inspect the running app**

Open the client parser in the in-app browser, switch between all and custom modes, save each mode, select Novosibirsk and dentistry, and verify layout, focus, dark theme, API payloads, and start-page behavior.

- [ ] **Step 3: Run a disposable real 2GIS smoke test**

Use the installed parser-2gis runtime against `https://2gis.ru/novosibirsk/search/стоматологии/filters/sort=name`, write output only beneath `backend/data/parser_output`, and verify more than 50 distinct cards are produced without importing them into SQLite. Remove the disposable output after counting it.

- [ ] **Step 4: Fix any verification defect with RED/GREEN evidence**

Add a focused regression test before each correction, run it failing, apply the smallest fix, and rerun it passing.

- [ ] **Step 5: Commit and push verification fixes if any**

```powershell
git add backend/main.py backend/database.py backend/parser.py backend/tests/test_parser_start_page.py src/pages/parserSettings.ts src/pages/ClientsPage.tsx src/pages/ParserControlPanel.tsx src/pages/ClientsPage.test.tsx src/styles.css src/premium-dark.css
git commit -m "fix: harden unlimited 2gis parsing"
git push origin main
```

- [ ] **Step 6: Verify remote parity**

Run:

```powershell
git status --short
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Expected: clean worktree and identical local/remote SHAs.
