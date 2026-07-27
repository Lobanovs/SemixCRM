# OpenCode Go Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a working OpenCode Go settings page that securely masks the saved key, applies settings without restart, verifies the connection, and powers the existing client-message generator.

**Architecture:** A focused `backend.ai.settings` module owns local SQLite persistence and safe serialization. `backend.ai.client.load_settings()` resolves database overrides before environment fallbacks, while FastAPI exposes small settings/test endpoints. A dedicated React `SettingsPage` consumes those endpoints and replaces the current placeholder.

**Tech Stack:** Python 3, FastAPI, SQLite, httpx, unittest, React 19, TypeScript, Vitest, Testing Library, Lucide React, plain CSS.

## Global Constraints

- Support OpenCode Go only at `https://opencode.ai/zen/go/v1`.
- Never return or log a complete API key.
- Keep the SQLite database under ignored `backend/data/`.
- Apply saved settings to the next AI request without restarting.
- Offer only OpenCode Go models compatible with `/chat/completions`.
- Preserve the existing environment-variable configuration as fallback.

---

### Task 1: Persist and resolve OpenCode Go settings

**Files:**
- Create: `backend/ai/settings.py`
- Modify: `backend/ai/client.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_ai_settings.py`

**Interfaces:**
- Produces: `SUPPORTED_MODELS`, `init_settings_schema()`, `read_stored_settings()`, `save_settings(api_key, model, timeout)`, `remove_saved_key()`, and `safe_settings()`.
- Consumes: `backend.database._connect` and existing environment variables. `backend.ai.client.load_settings()` translates stored values into `AiSettings` to avoid a circular import.

- [ ] **Step 1: Write failing persistence and precedence tests**

```python
class AiSettingsStorageTests(unittest.TestCase):
    def test_safe_settings_never_returns_the_key(self) -> None:
        save_settings(api_key="go-secret-1234", model="deepseek-v4-flash", timeout=45)
        public = safe_settings()
        self.assertNotIn("go-secret-1234", repr(public))
        self.assertTrue(public["api_key_configured"])

    @patch.dict(os.environ, {"OPENCODE_API_KEY": "env-key"}, clear=False)
    def test_database_key_takes_precedence_and_delete_disables_it(self) -> None:
        save_settings(api_key="db-key", model="deepseek-v4-flash", timeout=45)
        self.assertEqual("db-key", load_settings().api_key)
        remove_saved_key()
        self.assertEqual("", load_settings().api_key)
```

- [ ] **Step 2: Run the new backend test and verify RED**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_settings -v`
Expected: FAIL because `backend.ai.settings` and its schema do not exist.

- [ ] **Step 3: Implement the SQLite settings module**

Create an `ai_settings` singleton table with nullable `api_key`, supported model validation, timeout validation, safe key masking, and an explicit empty-string override for key removal. Use `deepseek-v4-flash` as the new default chat-completions model.

- [ ] **Step 4: Integrate database precedence into the AI client**

Update `load_settings()` so a stored row wins over environment values, a nullable stored key falls back to `OPENCODE_API_KEY`, and an empty stored key explicitly disables AI.

- [ ] **Step 5: Run the backend settings test and verify GREEN**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_settings -v`
Expected: all storage and resolution tests pass.

### Task 2: Expose safe settings and connection-test API

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/ai/client.py`
- Test: `backend/tests/test_ai_settings.py`

**Interfaces:**
- Produces: `GET /api/ai/settings`, `PUT /api/ai/settings`, `DELETE /api/ai/settings/key`, `POST /api/ai/settings/test`.
- Consumes: Task 1 persistence functions and `AiClient.complete()`.

- [ ] **Step 1: Write failing API tests**

```python
def test_settings_api_masks_key(self) -> None:
    response = self.client.put("/api/ai/settings", json={
        "api_key": "go-secret-1234",
        "model": "deepseek-v4-flash",
        "timeout": 45,
    }, headers={"X-Requested-With": "SemixCRM"})
    self.assertEqual(200, response.status_code)
    self.assertNotIn("go-secret-1234", response.text)

def test_connection_check_maps_rejected_key(self) -> None:
    with patch("backend.main.AiClient.complete", side_effect=AiError("Ключ OpenCode отклонён (401)")):
        response = self.client.post("/api/ai/settings/test", json={
            "api_key": "bad-key",
            "model": "deepseek-v4-flash",
            "timeout": 45,
        }, headers={"X-Requested-With": "SemixCRM"})
    self.assertEqual(502, response.status_code)
```

- [ ] **Step 2: Run the API tests and verify RED**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_settings.AiSettingsApiTests -v`
Expected: FAIL with missing routes.

- [ ] **Step 3: Implement request models and endpoints**

Use optional `api_key` on save/test, validate model and timeout through Pydantic and the settings module, preserve the stored key when omitted, and protect PUT/DELETE/POST with `guard_powerful_action`.

- [ ] **Step 4: Implement connection verification**

Construct a temporary `AiClient` from the submitted or effective settings and issue a minimal `chat/completions` request. Convert `AiDisabledError` to HTTP 400 and `AiError` to HTTP 502 without logging the submitted key.

- [ ] **Step 5: Run the complete backend settings tests and verify GREEN**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_settings -v`
Expected: all API and storage tests pass.

### Task 3: Build the OpenCode Go settings page

**Files:**
- Create: `src/pages/SettingsPage.tsx`
- Create: `src/pages/SettingsPage.test.tsx`
- Modify: `src/App.tsx`
- Modify: `src/styles.css`

**Interfaces:**
- Consumes: Task 2 REST endpoints through `apiRequest`.
- Produces: `SettingsPage` default React component and accessible settings UI.

- [ ] **Step 1: Write failing frontend interaction tests**

```tsx
it('loads masked status and saves a replacement key', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', createSettingsFetch())
  render(<SettingsPage />)
  expect(await screen.findByText('OpenCode Go подключён')).toBeInTheDocument()
  await user.type(screen.getByLabelText('API-ключ OpenCode Go'), 'new-key')
  await user.click(screen.getByRole('button', { name: 'Сохранить настройки' }))
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/ai/settings'),
    expect.objectContaining({ method: 'PUT' }),
  )
})

it('tests an unsaved key and reports success', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', createSettingsFetch())
  render(<SettingsPage />)
  await user.type(await screen.findByLabelText('API-ключ OpenCode Go'), 'test-key')
  await user.click(screen.getByRole('button', { name: 'Проверить подключение' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Подключение работает')
})
```

- [ ] **Step 2: Run the settings-page test and verify RED**

Run: `npm run test:frontend -- src/pages/SettingsPage.test.tsx`
Expected: FAIL because `SettingsPage` does not exist.

- [ ] **Step 3: Use UI/UX Pro Max recommendations**

Run the design-system search for a dense local SaaS settings dashboard, the form-feedback UX search, and React stack guidance. Apply the existing Semix CRM tokens, visible labels, keyboard focus, pending states, inline status feedback, and Lucide icons.

- [ ] **Step 4: Implement the page and navigation**

Create the status card, key field with show/hide action, supported-model select, timeout input, read-only endpoint, save/test actions, and two-step inline key removal confirmation. Update `App.tsx` so the settings navigation item renders `SettingsPage`.

- [ ] **Step 5: Add light/dark CSS and accessible states**

Add page-scoped desktop styles, focus-visible treatment, disabled/loading states, status colors that do not rely on color alone, and dark-theme overrides. Keep responsive behavior functional without mobile-specific redesign.

- [ ] **Step 6: Run the page tests and verify GREEN**

Run: `npm run test:frontend -- src/pages/SettingsPage.test.tsx`
Expected: all settings-page tests pass.

### Task 4: Update integration guidance and complete verification

**Files:**
- Modify: `src/pages/ClientMessageModal.tsx`
- Modify: `src/pages/ClientMessageModal.test.tsx`
- Modify: `README.md`
- Modify if required for deterministic baseline: `src/pages/SchedulePage.test.tsx`

**Interfaces:**
- Consumes: working settings page and existing AI status endpoint.
- Produces: current UI guidance and a fully verified repository state.

- [ ] **Step 1: Write a failing guidance test**

Replace the old PowerShell `OPENCODE_API_KEY` instructions with a direct instruction to open the Semix CRM settings page, then run the focused modal test and verify that the old expectation fails.

- [ ] **Step 2: Update user guidance and README**

Document the OpenCode Go settings screen, local key storage, supported model selection, connection test, environment fallback, and the fact that no backend restart is needed.

- [ ] **Step 3: Make date-sensitive schedule tests deterministic if they still fail**

Freeze Vitest system time to the week represented by the fixtures and restore real timers after each test. Do not alter schedule production behavior.

- [ ] **Step 4: Run full backend verification**

Run: `backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v`
Expected: zero failures.

- [ ] **Step 5: Run full frontend verification**

Run: `npm run test:frontend`
Expected: zero failures.

- [ ] **Step 6: Run production build**

Run: `npm run build`
Expected: exit code 0.

- [ ] **Step 7: Verify the settings workflow in the local browser**

Open the settings section, check loading/status rendering, input visibility toggle, model selection, validation, and removal confirmation without entering or exposing a real key.

- [ ] **Step 8: Review and publish**

Inspect `git diff`, ensure no secret or generated data is staged, commit the complete intended working tree, push `main` to `origin`, and confirm the remote commit SHA.
