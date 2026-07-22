# Profi.ru and YouDo Freelance Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Completed steps use checked boxes (`- [x]`) for tracking.

**Goal:** Remove Workzilla, make Profi.ru and YouDo parsing honest and functional with saved Chrome sessions, harden public adapters, and show five generated source badges in the desktop freelance UI.

**Architecture:** Keep HTTP collection for Kwork, FL.ru, and Freelance.ru. Split browser collection into a shared navigation/state layer plus source-specific Profi.ru and YouDo HTML parsers; YouDo retries a confirmed headless block once in headed minimized Chrome. Put source identity in one frontend metadata module consumed by settings, status cards, filters, and order cards.

**Tech Stack:** Python 3, FastAPI, Playwright sync API, BeautifulSoup, SQLite, React, TypeScript, Vite, Vitest, Testing Library, generated WebP assets.

## Global Constraints

- Supported sources are exactly `kwork`, `fl`, `freelance_ru`, `profi`, and `youdo`.
- Do not delete an existing Workzilla browser profile or historical database rows.
- Do not store cookies, credentials, personal page HTML, or live order contents in Git fixtures or terminal output.
- Do not bypass CAPTCHA or access challenges.
- Profi.ru and YouDo use isolated persistent Chrome profiles.
- YouDo may retry a confirmed headless block exactly once in headed minimized Chrome.
- An unrecognized page with zero cards is `error`, not `empty`.
- Generated badges are original Semix CRM identifiers, not copies of official trademarks.
- Desktop is the primary viewport; mobile-specific composition is out of scope, but horizontal overflow is not allowed.
- Every implementation task follows red-green-refactor, then commits and pushes to `origin/main`.

---

### Task 1: Remove Workzilla and sanitize saved settings

**Files:**
- Modify: `backend/freelance/models.py`
- Modify: `backend/freelance/adapters/browser.py`
- Modify: `backend/freelance/adapters/registry.py`
- Modify: `backend/freelance/browser_profile.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/test_freelance_adapters.py`
- Modify: `backend/tests/test_freelance_api.py`
- Modify: `backend/tests/test_freelance_orders.py`

**Interfaces:**
- Produces: `FREELANCE_SOURCES == ("kwork", "fl", "freelance_ru", "profi", "youdo")`.
- Produces: `AUTH_URLS` with only `profi` and `youdo`.
- Produces: `adapter_registry()` with the same five source keys.

- [x] **Step 1: Write failing source-list and legacy-settings tests**

```python
def test_registry_contains_only_supported_sources(self) -> None:
    self.assertEqual({"kwork", "fl", "freelance_ru", "profi", "youdo"}, set(adapter_registry()))

def test_legacy_workzilla_setting_is_filtered(self) -> None:
    database.save_freelance_settings(FreelanceSettings(sources=("workzilla", "profi")))
    self.assertEqual(["profi"], database.get_freelance_settings()["sources"])

def test_workzilla_auth_endpoint_is_removed(self) -> None:
    response = self.client.post("/api/freelance/sources/workzilla/auth")
    self.assertEqual(404, response.status_code)
```

- [x] **Step 2: Run the focused tests and verify RED**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_freelance_adapters backend.tests.test_freelance_api backend.tests.test_freelance_orders -v`

Expected: failures show Workzilla still exists in the model, registry, and auth route.

- [x] **Step 3: Remove Workzilla and reduce the API source limit**

```python
FREELANCE_SOURCES = ("kwork", "fl", "freelance_ru", "profi", "youdo")

AUTH_URLS = {
    "profi": "https://profi.ru/backoffice/a.php",
    "youdo": "https://youdo.com/tasks",
}

class FreelanceSettingsRequest(BaseModel):
    sources: list[str] = Field(min_length=1, max_length=5)
```

Delete `WorkzillaAdapter`, its registry import/entry, and Workzilla-specific test expectations. Keep database filtering based on `FREELANCE_SOURCES`; do not delete profile directories or rows.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2.

Expected: all selected tests pass.

- [x] **Step 5: Commit and push**

```powershell
git add backend/freelance/models.py backend/freelance/adapters/browser.py backend/freelance/adapters/registry.py backend/freelance/browser_profile.py backend/main.py backend/tests/test_freelance_adapters.py backend/tests/test_freelance_api.py backend/tests/test_freelance_orders.py
git commit -m "refactor: remove workzilla freelance source"
git push origin main
```

### Task 2: Add explicit browser page states and headed-session support

**Files:**
- Modify: `backend/freelance/adapters/browser.py`
- Modify: `backend/freelance/browser_profile.py`
- Modify: `backend/tests/test_freelance_adapters.py`

**Interfaces:**
- Produces: `BrowserPageState(status: str, error: str = "", auth_required: bool = False)`.
- Produces: `BrowserAdapter._collect_once(settings, *, headless: bool) -> AdapterResult`.
- Produces: `persistent_browser_factory(source: str | None = None, headless: bool = True) -> PersistentBrowserSession`.

- [x] **Step 1: Write failing classification and factory tests**

```python
def test_login_page_with_http_200_is_auth_required(self) -> None:
    page = FakePage(url="https://profi.ru/backoffice/a.php", title="Вход на Профи.ру", html="<input type='password'>")
    result = ProfiAdapter(browser_factory=FakeBrowserFactory(page, status=200)).collect(FreelanceSettings())
    self.assertEqual("auth_required", result.status)
    self.assertTrue(result.auth_required)

def test_unknown_empty_markup_is_error(self) -> None:
    page = FakePage(url="https://profi.ru/backoffice/a.php", title="Профи", html="<main></main>")
    result = ProfiAdapter(browser_factory=FakeBrowserFactory(page, status=200)).collect(FreelanceSettings())
    self.assertEqual("error", result.status)

def test_persistent_factory_forwards_headless_mode(self) -> None:
    with patch("backend.freelance.browser_profile.PersistentBrowserSession") as session_type:
        persistent_browser_factory("youdo", headless=False)
        session_type.assert_called_once_with(source="youdo", headless=False)
```

- [x] **Step 2: Run tests and verify RED**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_freelance_adapters -v`

Expected: missing explicit page-state handling and unsupported `headless` factory argument.

- [x] **Step 3: Implement the shared state flow**

```python
@dataclass(frozen=True)
class BrowserPageState:
    status: str
    error: str = ""
    auth_required: bool = False

def persistent_browser_factory(source: str | None = None, headless: bool = True) -> PersistentBrowserSession:
    return PersistentBrowserSession(source=source, headless=headless)
```

Make `_create_browser(headless=True)` support injected factories accepting zero, one, or two positional arguments. `_collect_once` must inspect response status, final URL, title, and content before parsing. It returns `empty` only when `classify_page` reports a confirmed empty state. Close every browser in `finally`.

For `PersistentBrowserSession(headless=False)`, add Chrome launch args `--start-minimized` without changing the login helper behavior.

- [x] **Step 4: Run tests and verify GREEN**

Run the command from Step 2.

Expected: all adapter tests pass.

- [x] **Step 5: Commit and push**

```powershell
git add backend/freelance/adapters/browser.py backend/freelance/browser_profile.py backend/tests/test_freelance_adapters.py
git commit -m "feat: classify freelance browser pages"
git push origin main
```

### Task 3: Implement the Profi.ru adapter

**Files:**
- Create: `backend/tests/fixtures/freelance/profi_orders.html`
- Create: `backend/tests/fixtures/freelance/profi_empty.html`
- Modify: `backend/freelance/adapters/browser.py`
- Modify: `backend/tests/test_freelance_adapters.py`

**Interfaces:**
- Produces: `ProfiAdapter.parse_html(html: str, page_url: str) -> list[FreelanceOrder]`.
- Produces: source-specific `classify_page` and dynamic-feed expansion.

- [x] **Step 1: Inspect only structural metadata from the saved profile**

Close the exact login helper processes if they still own the profiles, then run a diagnostic that prints only final URL, title, HTTP status, selector counts, link path patterns, and non-sensitive class names. Do not print text, cookies, request headers, or HTML.

- [x] **Step 2: Create sanitized fixtures and failing parser tests**

```python
def test_profi_fixture_extracts_order_fields(self) -> None:
    html = (FIXTURES / "profi_orders.html").read_text(encoding="utf-8")
    order = ProfiAdapter().parse_html(html, "https://profi.ru/backoffice/a.php")[0]
    self.assertEqual("profi", order.source)
    self.assertTrue(order.external_id.startswith("profi-"))
    self.assertEqual("https://profi.ru/backoffice/order/12345", order.url)
    self.assertEqual(5000, order.budget_min)

def test_profi_confirmed_empty_fixture_is_empty(self) -> None:
    state = ProfiAdapter().classify_html(200, "Профи", "https://profi.ru/backoffice/a.php", fixture("profi_empty.html"))
    self.assertEqual("empty", state.status)
```

- [x] **Step 3: Run the two tests and verify RED**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_freelance_adapters.FreelanceAdapterTests.test_profi_fixture_extracts_order_fields backend.tests.test_freelance_adapters.FreelanceAdapterTests.test_profi_confirmed_empty_fixture_is_empty -v`

Expected: missing `parse_html`/`classify_html` behavior.

- [x] **Step 4: Implement Profi selectors from observed structure**

Use BeautifulSoup against page content. Derive `external_id` from the stable order URL or data attribute, resolve relative links with `absolute_url`, and pass normalized title/description/budget/category through `order_from_card`. Expand the feed until external IDs stop growing for three checks or the safety limit is reached.

- [x] **Step 5: Run the full adapter tests and verify GREEN**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_freelance_adapters -v`

Expected: all tests pass.

- [x] **Step 6: Commit and push**

```powershell
git add backend/freelance/adapters/browser.py backend/tests/test_freelance_adapters.py backend/tests/fixtures/freelance/profi_orders.html backend/tests/fixtures/freelance/profi_empty.html
git commit -m "feat: parse profi freelance orders"
git push origin main
```

### Task 4: Implement YouDo parsing and one headed fallback

**Files:**
- Create: `backend/tests/fixtures/freelance/youdo_tasks.html`
- Create: `backend/tests/fixtures/freelance/youdo_empty.html`
- Modify: `backend/freelance/adapters/browser.py`
- Modify: `backend/tests/test_freelance_adapters.py`

**Interfaces:**
- Produces: `YoudoAdapter.parse_html(html: str, page_url: str) -> list[FreelanceOrder]`.
- Produces: `YoudoAdapter.collect(settings) -> AdapterResult`, headless first and headed once only after `blocked`.

- [x] **Step 1: Write failing block/fallback/parser tests**

```python
def test_youdo_403_is_blocked(self) -> None:
    state = YoudoAdapter().classify_html(403, "Доступ ограничен", "https://youdo.com/tasks", "<main></main>")
    self.assertEqual("blocked", state.status)

def test_youdo_retries_blocked_headless_once_in_headed_browser(self) -> None:
    factory = RecordingFactory([blocked_page(), tasks_page()])
    result = YoudoAdapter(browser_factory=factory).collect(FreelanceSettings())
    self.assertEqual([True, False], factory.headless_modes)
    self.assertEqual("done", result.status)

def test_youdo_fixture_extracts_task_fields(self) -> None:
    html = fixture("youdo_tasks.html")
    order = YoudoAdapter().parse_html(html, "https://youdo.com/tasks")[0]
    self.assertEqual("youdo", order.source)
    self.assertTrue(order.external_id.startswith("youdo-"))
```

- [x] **Step 2: Run the tests and verify RED**

Run the three named tests with `python -m unittest ... -v`.

Expected: 403 is not classified and no headed fallback exists.

- [x] **Step 3: Inspect headed YouDo structure without printing content**

Use the saved profile with `headless=False` and collect only status, URL, title, stable task-link patterns, selector counts, and class names. Build synthetic fixtures by hand from that structure.

- [x] **Step 4: Implement classification, parsing, and fallback**

```python
def collect(self, settings: FreelanceSettings) -> AdapterResult:
    result = self._collect_once(settings, headless=True)
    if result.status != "blocked":
        return result
    return self._collect_once(settings, headless=False)
```

Classify 401/403/429, access-restricted titles, challenge markers, and CAPTCHA as `blocked`. Do not retry `auth_required`, `empty`, `done`, or generic parser errors.

- [x] **Step 5: Run full adapter tests and verify GREEN**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_freelance_adapters -v`

Expected: all tests pass.

- [x] **Step 6: Commit and push**

```powershell
git add backend/freelance/adapters/browser.py backend/tests/test_freelance_adapters.py backend/tests/fixtures/freelance/youdo_tasks.html backend/tests/fixtures/freelance/youdo_empty.html
git commit -m "feat: parse youdo tasks with browser fallback"
git push origin main
```

### Task 5: Retry transient public-source failures

**Files:**
- Modify: `backend/freelance/adapters/base.py`
- Modify: `backend/tests/test_freelance_adapters.py`

**Interfaces:**
- Produces: `PublicHttpAdapter(..., max_attempts: int = 2, retry_delay: float = 0.25, sleeper: Callable[[float], None] = time.sleep)`.

- [x] **Step 1: Write a failing timeout-then-success test**

```python
def test_public_adapter_retries_one_timeout(self) -> None:
    client_factory = SequenceClientFactory([httpx.ReadTimeout("slow"), fixture_response("kwork_projects.html")])
    result = KworkAdapter(client_factory=client_factory, retry_delay=0, sleeper=lambda _: None).collect(FreelanceSettings())
    self.assertEqual("done", result.status)
    self.assertEqual(2, client_factory.calls)
```

- [x] **Step 2: Run the test and verify RED**

Run the named unittest.

Expected: constructor arguments or retry behavior are missing.

- [x] **Step 3: Implement bounded retry**

Retry only `httpx.TimeoutException` and `httpx.NetworkError`; preserve the current HTTP status and parse error messages. Use at most two total attempts.

- [x] **Step 4: Run adapter tests and verify GREEN**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_freelance_adapters -v`

Expected: all tests pass.

- [x] **Step 5: Commit and push**

```powershell
git add backend/freelance/adapters/base.py backend/tests/test_freelance_adapters.py
git commit -m "fix: retry transient freelance source requests"
git push origin main
```

### Task 6: Generate and integrate five source badges

**Files:**
- Create: `src/assets/freelance/kwork.webp`
- Create: `src/assets/freelance/fl.webp`
- Create: `src/assets/freelance/freelance-ru.webp`
- Create: `src/assets/freelance/profi.webp`
- Create: `src/assets/freelance/youdo.webp`
- Create: `src/pages/freelanceSources.ts`
- Create: `src/pages/freelanceSources.test.ts`

**Interfaces:**
- Produces: `FREELANCE_SOURCE_KEYS`, `BROWSER_SOURCE_KEYS`, `FreelanceSourceKey`, and `FREELANCE_SOURCE_META`.

- [x] **Step 1: Write the failing metadata test**

```typescript
import { FREELANCE_SOURCE_KEYS, FREELANCE_SOURCE_META } from './freelanceSources'

it('defines five distinct source badges without Workzilla', () => {
  expect(FREELANCE_SOURCE_KEYS).toEqual(['kwork', 'fl', 'freelance_ru', 'profi', 'youdo'])
  expect(new Set(FREELANCE_SOURCE_KEYS.map((key) => FREELANCE_SOURCE_META[key].icon)).size).toBe(5)
  expect(JSON.stringify(FREELANCE_SOURCE_META)).not.toContain('workzilla')
})
```

- [x] **Step 2: Run the test and verify RED**

Run: `npm run test:frontend -- src/pages/freelanceSources.test.ts`

Expected: module does not exist.

- [x] **Step 3: Generate the assets with the built-in image tool**

Issue one generation call per badge. Shared prompt constraints: square flat/minimal app badge, clean geometric symbol, no photorealism, no 3D, no watermark, no tiny text, strong silhouette, Semix CRM light-dashboard use. Use green K/marketplace for Kwork, blue FL/briefcase for FL.ru, purple project cards for Freelance.ru, raspberry specialist-client symbol for Profi.ru, and blue-orange completed-task symbol for YouDo.

Copy final outputs into `src/assets/freelance`, resize to 192×192, encode WebP, and visually inspect all five files.

- [x] **Step 4: Implement the metadata module**

```typescript
export const FREELANCE_SOURCE_KEYS = ['kwork', 'fl', 'freelance_ru', 'profi', 'youdo'] as const
export const BROWSER_SOURCE_KEYS = ['profi', 'youdo'] as const

export const FREELANCE_SOURCE_META = {
  kwork: { label: 'Kwork', icon: kworkIcon, accent: 'green', url: 'https://kwork.ru/projects' },
  fl: { label: 'FL.ru', icon: flIcon, accent: 'blue', url: 'https://www.fl.ru/projects/' },
  freelance_ru: { label: 'Freelance.ru', icon: freelanceRuIcon, accent: 'purple', url: 'https://freelance.ru/task' },
  profi: { label: 'Profi.ru', icon: profiIcon, accent: 'pink', url: 'https://profi.ru/backoffice/a.php' },
  youdo: { label: 'YouDo', icon: youdoIcon, accent: 'blue', url: 'https://youdo.com/tasks' },
} as const
```

- [x] **Step 5: Run the metadata test and production build**

Run: `npm run test:frontend -- src/pages/freelanceSources.test.ts`

Run: `npm run build`

Expected: both commands exit 0.

- [x] **Step 6: Commit and push**

```powershell
git add src/assets/freelance src/pages/freelanceSources.ts src/pages/freelanceSources.test.ts
git commit -m "feat: add freelance source badges"
git push origin main
```

### Task 7: Rebuild source controls and status cards

**Files:**
- Create: `src/pages/FreelancePage.test.tsx`
- Modify: `src/pages/FreelancePage.tsx`
- Modify: `src/styles.css`

**Interfaces:**
- Consumes: `FREELANCE_SOURCE_KEYS`, `BROWSER_SOURCE_KEYS`, and `FREELANCE_SOURCE_META`.
- Produces: source cards with image, label, state, count/time, recovery action, and no Workzilla controls.

- [x] **Step 1: Write failing UI tests**

```typescript
it('shows five named source badges and no Workzilla', async () => {
  render(<FreelancePage />)
  for (const label of ['Kwork', 'FL.ru', 'Freelance.ru', 'Profi.ru', 'YouDo']) {
    expect(await screen.findByAltText(`${label} — значок источника`)).toBeVisible()
  }
  expect(screen.queryByText('Workzilla')).not.toBeInTheDocument()
})

it('offers login for auth_required and retry for error', async () => {
  render(<FreelancePage />)
  expect(await screen.findByRole('button', { name: 'Войти в Profi.ru' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Повторить проверку Kwork' })).toBeVisible()
})
```

Mock every endpoint loaded by `FreelancePage`: orders, stats, settings, source statuses, sniper status, and run history when requested.

- [x] **Step 2: Run the tests and verify RED**

Run: `npm run test:frontend -- src/pages/FreelancePage.test.tsx`

Expected: Workzilla is present and generated badge/status actions are absent.

- [x] **Step 3: Implement source metadata rendering and recovery actions**

Replace local source arrays/mappings with `freelanceSources.ts`. Add a reusable `SourceMark` image component and `SourceStatusCard`. Map statuses to Russian labels: `done → Готово`, `empty → Нет новых`, `auth_required → Требуется вход`, `blocked → Доступ ограничен`, `error → Ошибка`.

Use `openAuth` for Profi/YouDo login or blocked recovery and `checkNow` for retry. Keep text and status icon in addition to color, `role="alert"` for errors, and `aria-live="polite"` for checks.

- [x] **Step 4: Add focused desktop CSS**

Add `.freelance-source-card`, `.source-mark`, `.source-state`, `.source-recovery-action`, dark-theme rules, 44 px actions, visible focus rings, reserved image dimensions, and a one-column fallback below the existing breakpoint. Do not add new raw colors when an existing Semix token/class can express the state.

- [x] **Step 5: Run focused and full frontend verification**

Run: `npm run test:frontend -- src/pages/FreelancePage.test.tsx src/pages/freelanceSources.test.ts`

Run: `npm run test:frontend`

Run: `npm run build`

Expected: all commands exit 0.

- [x] **Step 6: Commit and push**

```powershell
git add src/pages/FreelancePage.tsx src/pages/FreelancePage.test.tsx src/styles.css
git commit -m "feat: improve freelance source controls"
git push origin main
```

### Task 8: Update documentation and perform live verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-22-freelance-profi-youdo.md`

**Interfaces:**
- Produces: accurate five-source documentation and checked plan boxes.

- [x] **Step 1: Update README source lists and environment variables**

Change the architecture diagram and freelance table from six sources to five, remove `FREELANCE_WORKZILLA_URL`, explain YouDo headed fallback, and retain the manual login/profile-safety instructions.

- [x] **Step 2: Run the full automated suite**

Run: `backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v`

Run: `npm run test:frontend`

Run: `npm run build`

Expected: zero failures and build exit 0.

- [x] **Step 3: Run live adapters without printing order contents**

For each source output only source, status, count, error, missing-title count, missing-URL count, and missing-description count. Confirm Kwork/FL.ru/Freelance.ru directly. Confirm Profi.ru using the saved profile. Confirm YouDo headless behavior and its headed fallback.

- [x] **Step 4: Exercise the API and frontend**

Run one manual `/api/freelance/sniper/check`, inspect `/api/freelance/sources`, and verify every status is honest. In the desktop UI verify settings save, five badges render, Workzilla is absent, login/retry actions work, and no horizontal overflow appears in light and dark themes.

- [x] **Step 5: Mark completed checkboxes, inspect final diff, commit, and push**

```powershell
git add README.md docs/superpowers/plans/2026-07-22-freelance-profi-youdo.md
git commit -m "docs: update freelance parser guidance"
git push origin main
git status -sb
git rev-parse HEAD
git rev-parse origin/main
```

Expected: clean `main`, and local/remote commit hashes match.
