# Рабочий раздел «Фриланс» и локальный снайпер заказов Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded Freelance page with a persisted order CRM, seven source adapters, a local sniper worker, and single-recipient Telegram notifications.

**Architecture:** The backend normalizes all sources into one `FreelanceOrder` model. Public/API adapters use HTTP, authenticated sources use a persistent Chromium profile, and a shared service deduplicates, scores, persists, and notifies. FastAPI exposes CRUD, source health, settings, and sniper controls; the React page reads only these endpoints.

**Tech Stack:** FastAPI, Pydantic 2, SQLite, `httpx`, BeautifulSoup, Playwright Python, React, TypeScript, Vite, Lucide icons.

## Global Constraints

- The sniper works only while the local Semix CRM backend is running.
- Seven sources are independently enabled: Kwork, FL.ru, Freelance.ru, Workzilla, Freelancehunt, Profi.ru, YouDo.
- The implementation never bypasses CAPTCHA, access restrictions, or platform protections.
- Credentials are never stored in source code; browser cookies remain in a local Chromium profile.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_ID` are read only from environment variables.
- Empty sources and empty database states stay empty; no fake/demo orders are inserted.
- One order is notified at most once for the configured Telegram chat ID.
- Existing Semix CRM light/dark design tokens, Lucide icons, visible focus states, and responsive behavior remain in use.
- Development follows TDD: every production behavior starts with a failing test.

---

## File Map

Create these focused modules:

- `backend/freelance/__init__.py` — package marker and public exports.
- `backend/freelance/models.py` — dataclasses, enums, and adapter result types.
- `backend/freelance/scoring.py` — deterministic relevance scoring.
- `backend/freelance/adapters/base.py` — adapter protocol and shared HTTP/browser helpers.
- `backend/freelance/adapters/public.py` — Kwork, FL.ru, Freelance.ru, and Freelancehunt adapters.
- `backend/freelance/adapters/browser.py` — Workzilla, Profi.ru, and YouDo adapters using persistent Chromium.
- `backend/freelance/adapters/registry.py` — source registry and adapter construction.
- `backend/freelance/telegram.py` — single-recipient Telegram notifier.
- `backend/freelance/sniper.py` — polling worker lifecycle and per-source result isolation.
- `backend/tests/fixtures/freelance/` — checked-in HTML/API fixtures only, never production records.

Modify these existing files:

- `backend/database.py` — SQLite schema, migrations, repositories, and serialization.
- `backend/main.py` — Freelance Pydantic requests, endpoints, and worker lifecycle hooks.
- `backend/requirements.txt` — `beautifulsoup4` and `playwright` dependencies.
- `backend/README.md` — local setup, environment variables, and browser login instructions.
- `.gitignore` — ignore `.env`, browser profiles, and freelance fixture output.
- `.env.example` — safe configuration template with no real token.
- `src/pages/FreelancePage.tsx` — API-backed page and interactions.
- `src/styles.css` — loading, error, source status, sniper, and modal states.

Create these test modules:

- `backend/tests/test_freelance_orders.py`
- `backend/tests/test_freelance_adapters.py`
- `backend/tests/test_freelance_sniper.py`
- `backend/tests/test_freelance_api.py`

---

### Task 1: Persisted freelance orders and deterministic scoring

**Files:**
- Create: `backend/freelance/__init__.py`
- Create: `backend/freelance/models.py`
- Create: `backend/freelance/scoring.py`
- Modify: `backend/database.py` in `init_db()` and after the schedule repository functions
- Test: `backend/tests/test_freelance_orders.py`

**Interfaces:**
- Produces `FreelanceOrder`, `FreelanceOrderFilters`, `FreelanceSettings`, `SourceStatus` and `score_order(order, settings) -> tuple[int, list[str]]`.
- Produces database functions `list_freelance_orders`, `create_freelance_order`, `update_freelance_order`, `archive_freelance_order`, `freelance_stats`, `get_freelance_settings`, `save_freelance_settings`, `record_source_check`, `list_source_statuses`, `record_notification`, and `notification_sent`.

- [ ] **Step 1: Write the failing repository and scoring tests.**

```python
# backend/tests/test_freelance_orders.py
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database
from backend.freelance.models import FreelanceOrder, FreelanceOrderFilters, FreelanceSettings
from backend.freelance.scoring import score_order


class FreelanceOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "freelance.sqlite3"
        self.path_patch = patch.object(database, "DB_PATH", self.db_path)
        self.path_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_order_is_persisted_and_duplicate_external_id_is_rejected(self) -> None:
        order = FreelanceOrder(source="fl", external_id="fl-42", title="React CRM", url="https://fl.ru/projects/42")
        first = database.create_freelance_order(order)
        second = database.create_freelance_order(order)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(1, len(database.list_freelance_orders(FreelanceOrderFilters())))

    def test_filters_and_stats_use_only_saved_orders(self) -> None:
        database.create_freelance_order(FreelanceOrder(source="kwork", external_id="1", title="React site", budget_min=70000, status="Новый"))
        database.create_freelance_order(FreelanceOrder(source="fl", external_id="2", title="Copywriting", budget_min=10000, status="В работе"))
        result = database.list_freelance_orders(FreelanceOrderFilters(source="kwork", min_budget=50000))
        self.assertEqual(["React site"], [item["title"] for item in result])
        self.assertEqual(2, database.freelance_stats()["total"])

    def test_score_explains_keyword_and_budget_matches(self) -> None:
        order = FreelanceOrder(source="fl", external_id="3", title="Next.js CRM", description="Нужен сайт", budget_min=120000)
        settings = FreelanceSettings(keywords=["CRM", "Next.js"], min_budget=50000)
        score, reasons = score_order(order, settings)
        self.assertGreaterEqual(score, 70)
        self.assertIn("Совпадение ключевого слова в названии", " ".join(reasons))

    def test_empty_database_has_no_seed_orders(self) -> None:
        self.assertEqual([], database.list_freelance_orders(FreelanceOrderFilters()))
        self.assertEqual(0, database.freelance_stats()["total"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails for the missing model/repository.**

Run: `py -3 -m unittest backend.tests.test_freelance_orders -v`

Expected: FAIL with an import error for `backend.freelance` or a missing repository function, not a passing test.

- [ ] **Step 3: Implement the model, scoring, tables, and repository.**

Use a frozen dataclass with these exact fields:

```python
@dataclass(frozen=True)
class FreelanceOrder:
    source: str
    external_id: str
    title: str
    description: str = ""
    url: str = ""
    customer: str = ""
    categories: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    budget_min: int | None = None
    budget_max: int | None = None
    currency: str = "RUB"
    budget_text: str = ""
    published_at: str = ""
    discovered_at: str = ""
```

Create `freelance_orders`, `freelance_settings`, `freelance_source_checks`, and `freelance_notifications` tables in `init_db()` with unique `(source, external_id)` and an index on `published_at`. Store categories/tags/settings as JSON. A duplicate returns the existing serialized row and never inserts a second row.

Implement `score_order` with a 0–100 deterministic score: title keyword matches add 30 each up to 60, description/category matches add 10 each up to 20, budget at/above minimum adds 15, and an exclusion match returns score 0 with an exclusion reason. Missing budgets receive neither a bonus nor a penalty.

- [ ] **Step 4: Run the focused tests and the existing backend suite.**

Run: `py -3 -m unittest backend.tests.test_freelance_orders -v`

Expected: 4 tests pass.

Run: `py -3 -m unittest discover -s backend/tests -p "test_*.py" -v`

Expected: all existing schedule/parser tests and the 4 freelance tests pass.

- [ ] **Step 5: Commit the vertical slice.**

```powershell
git add backend/freelance backend/database.py backend/tests/test_freelance_orders.py
git commit -m "feat: persist freelance orders"
```

---

### Task 2: Seven source adapters and fixture parsing

**Files:**
- Create: `backend/freelance/adapters/base.py`
- Create: `backend/freelance/adapters/public.py`
- Create: `backend/freelance/adapters/browser.py`
- Create: `backend/freelance/adapters/registry.py`
- Create: `backend/tests/fixtures/freelance/fl_projects.html`
- Create: `backend/tests/fixtures/freelance/freelancehunt_projects.json`
- Create: `backend/tests/fixtures/freelance/kwork_projects.html`
- Create: `backend/tests/fixtures/freelance/freelance_ru_projects.html`
- Create: `backend/tests/test_freelance_adapters.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- `SourceAdapter.source -> str`, `SourceAdapter.requires_browser -> bool`, `SourceAdapter.collect(settings) -> AdapterResult`.
- `AdapterResult(source, status, orders, checked_at, error, auth_required)`.
- Registry keys are exactly `kwork`, `fl`, `freelance_ru`, `workzilla`, `freelancehunt`, `profi`, `youdo`.

- [ ] **Step 1: Add failing fixture tests for public adapters and registry coverage.**

```python
def test_fl_fixture_extracts_real_fields(self):
    result = FlAdapter().parse_html(self.fixture("fl_projects.html"))
    self.assertEqual("fl", result[0].source)
    self.assertEqual("fl-100", result[0].external_id)
    self.assertEqual("React CRM для бизнеса", result[0].title)
    self.assertEqual("https://www.fl.ru/projects/100/", result[0].url)

def test_registry_contains_all_requested_sources(self):
    self.assertEqual(
        {"kwork", "fl", "freelance_ru", "workzilla", "freelancehunt", "profi", "youdo"},
        set(adapter_registry()),
    )

def test_browser_adapter_reports_auth_required_without_session(self):
    result = WorkzillaAdapter(browser_factory=lambda: None).collect(FreelanceSettings())
    self.assertEqual("auth_required", result.status)
    self.assertTrue(result.auth_required)
```

- [ ] **Step 2: Run the adapter tests and confirm they fail because adapters/fixtures do not exist.**

Run: `py -3 -m unittest backend.tests.test_freelance_adapters -v`

Expected: FAIL with missing adapter imports or registry entries.

- [ ] **Step 3: Add dependencies and implement shared adapter contracts.**

Append these pinned-compatible ranges to `backend/requirements.txt`:

```text
beautifulsoup4>=4.13,<5
playwright>=1.54,<2
```

Implement public adapters with `httpx.Client`, a descriptive User-Agent, a 20-second timeout, and BeautifulSoup selectors from the checked-in fixtures. Implement Freelancehunt through its documented projects endpoint and parse the JSON response. Implement browser adapters through `sync_playwright().chromium.launch_persistent_context(user_data_dir=...)`; never accept a password argument.

- [ ] **Step 4: Run fixture tests and verify the registry.**

Run: `py -3 -m unittest backend.tests.test_freelance_adapters -v`

Expected: all parser fixture tests pass, including `auth_required` without a browser session.

- [ ] **Step 5: Commit adapters independently.**

```powershell
git add backend/freelance/adapters backend/tests/fixtures/freelance backend/tests/test_freelance_adapters.py backend/requirements.txt
git commit -m "feat: add freelance source adapters"
```

---

### Task 3: Local sniper worker and Telegram notifier

**Files:**
- Create: `backend/freelance/telegram.py`
- Create: `backend/freelance/sniper.py`
- Create: `backend/tests/test_freelance_sniper.py`
- Create: `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- `TelegramNotifier.send_order(order: dict[str, Any]) -> bool`.
- `FreelanceSniper.start() -> dict[str, Any]`, `stop() -> dict[str, Any]`, `status() -> dict[str, Any]`, `check_once() -> dict[str, Any]`.
- The worker receives an adapter registry and a notifier through dependency injection so tests never contact the network.

- [ ] **Step 1: Write failing tests for recipient restriction, dedupe notification, worker lifecycle, and source isolation.**

```python
def test_notifier_rejects_a_different_chat_id(self):
    notifier = TelegramNotifier(token="test", allowed_chat_id="800395558", transport=self.fake_transport)
    self.assertFalse(notifier.send_text("999", "blocked"))
    self.assertEqual([], self.fake_transport.calls)

def test_sniper_notifies_only_new_orders_and_keeps_source_error(self):
    sniper = FreelanceSniper(registry={"fl": NewAdapter(), "profi": ErrorAdapter()}, notifier=FakeNotifier())
    result = sniper.check_once()
    self.assertEqual(1, result["inserted"])
    self.assertEqual("error", result["sources"]["profi"]["status"])
    self.assertEqual(1, len(sniper.notifier.sent))

def test_start_and_stop_are_idempotent(self):
    sniper = FreelanceSniper(registry={}, notifier=FakeNotifier(), interval_seconds=60)
    self.assertEqual("running", sniper.start()["status"])
    self.assertEqual("running", sniper.start()["status"])
    self.assertEqual("stopped", sniper.stop()["status"])
```

- [ ] **Step 2: Run tests and verify they fail before implementation.**

Run: `py -3 -m unittest backend.tests.test_freelance_sniper -v`

Expected: FAIL with missing `TelegramNotifier` or `FreelanceSniper`.

- [ ] **Step 3: Implement the notifier and worker.**

The notifier calls `https://api.telegram.org/bot{token}/sendMessage` with `chat_id`, `text`, and `disable_web_page_preview=True`. It refuses any chat ID other than `TELEGRAM_ALLOWED_CHAT_ID` and returns `False` when either environment value is missing. The worker uses a `threading.Event`, a single daemon thread, a per-source result map, and `check_once()` that inserts orders, checks `notification_sent(source, external_id, chat_id)`, sends each new order once, and records success/error.

- [ ] **Step 4: Run sniper tests plus all backend tests.**

Run: `py -3 -m unittest backend.tests.test_freelance_sniper -v`

Expected: all lifecycle, isolation, and notification tests pass.

Run: `py -3 -m unittest discover -s backend/tests -p "test_*.py" -v`

Expected: all backend tests pass.

- [ ] **Step 5: Commit the worker and safe configuration template.**

```powershell
git add backend/freelance/telegram.py backend/freelance/sniper.py backend/tests/test_freelance_sniper.py .env.example .gitignore
git commit -m "feat: add local freelance sniper"
```

---

### Task 4: FastAPI Freelance API

**Files:**
- Create: `backend/tests/test_freelance_api.py`
- Modify: `backend/main.py`

**Interfaces:**
- `GET /api/freelance/orders`
- `POST /api/freelance/orders`
- `PUT /api/freelance/orders/{order_id}`
- `DELETE /api/freelance/orders/{order_id}`
- `GET /api/freelance/settings`
- `PUT /api/freelance/settings`
- `GET /api/freelance/sources`
- `GET /api/freelance/sniper/status`
- `POST /api/freelance/sniper/start`
- `POST /api/freelance/sniper/stop`
- `POST /api/freelance/sniper/check`
- `GET /api/freelance/runs`
- `POST /api/freelance/sources/{source}/auth`

- [ ] **Step 1: Write failing API tests.**

```python
def test_orders_endpoint_is_empty_without_seed_data(self):
    response = self.client.get("/api/freelance/orders")
    self.assertEqual(200, response.status_code)
    self.assertEqual([], response.json()["orders"])

def test_create_and_update_order_round_trip(self):
    created = self.client.post("/api/freelance/orders", json={"source": "manual", "title": "Новый лендинг", "url": "https://example.test/order"})
    self.assertEqual(201, created.status_code)
    order_id = created.json()["id"]
    updated = self.client.put(f"/api/freelance/orders/{order_id}", json={"status": "Написал", "next_step": "Жду ответа", "note": "Проверить завтра"})
    self.assertEqual("Написал", updated.json()["status"])

def test_sniper_controls_are_idempotent(self):
    self.assertEqual("running", self.client.post("/api/freelance/sniper/start").json()["status"])
    self.assertEqual("running", self.client.post("/api/freelance/sniper/start").json()["status"])
    self.assertEqual("stopped", self.client.post("/api/freelance/sniper/stop").json()["status"])
```

- [ ] **Step 2: Run API tests and verify missing routes fail.**

Run: `py -3 -m unittest backend.tests.test_freelance_api -v`

Expected: FAIL with 404 responses until routes are added.

- [ ] **Step 3: Add Pydantic request models and routes.**

Validate source names against the seven registry keys, status against the eight CRM statuses, `limit` and `interval_seconds` within safe bounds, and URL length. Return `422` for invalid input and `404` for missing orders. Create the singleton sniper after `init_db()` in lifespan and stop it during lifespan shutdown.

- [ ] **Step 4: Run API and full backend tests.**

Run: `py -3 -m unittest backend.tests.test_freelance_api -v`

Expected: all API tests pass.

Run: `py -3 -m unittest discover -s backend/tests -p "test_*.py" -v`

Expected: all existing and new backend tests pass.

- [ ] **Step 5: Commit the API layer.**

```powershell
git add backend/main.py backend/tests/test_freelance_api.py
git commit -m "feat: expose freelance API"
```

---

### Task 5: API-backed Freelance frontend

**Files:**
- Modify: `src/pages/FreelancePage.tsx`
- Modify: `src/styles.css`

**Interfaces:**
- `FreelancePage` fetches only `/api/freelance/*`; it must not contain a seeded `orders` array or hardcoded statistics.
- UI actions call the API and refresh the affected order/source/status state.

- [ ] **Step 1: Replace the hardcoded page with failing TypeScript behavior checks.**

Use the existing browser smoke harness to assert the current implementation is not acceptable:

```text
Open «Фриланс» → expect API request /api/freelance/orders
Inspect document.body.innerText → expect no «Telegram Mini App для доставки» when API returns []
Click «Добавить заказ» → submit title → expect POST /api/freelance/orders
Click «Снайпер активен» → expect POST /api/freelance/sniper/start
```

Run: `npm run build`

Expected before the change: build may pass, but the browser assertions fail because the page uses hardcoded `orders` and statistics.

- [ ] **Step 2: Implement API types and loading/error/empty state.**

Add `FreelanceOrder`, `FreelanceStats`, `FreelanceSettings`, `FreelanceSourceStatus`, and `FreelanceOrdersResponse` TypeScript types. Use `useEffect` to load orders, settings, source statuses, and sniper status from `VITE_API_BASE_URL ?? http://127.0.0.1:8000`. Render explicit loading, error, and empty states; never use fallback demo data.

- [ ] **Step 3: Implement interactive toolbar, order modal, statuses, and source panel.**

The toolbar filters local API data by query/source/status/category/minimum budget. The modal posts a manual order. Each card updates status/next step/note with `PUT`. The side panel renders the seven source toggles, interval, keywords, exclusions, minimum budget, start/stop/check buttons, auth-required action, and last-check errors. Use Lucide icons and the existing `MetricCard`, `SidePanel`, `StatusBadge`, `Tag`, and `EmptyState` components.

- [ ] **Step 4: Add responsive and dark-theme states.**

Append focused selectors in `src/styles.css` for `.freelance-source-status`, `.freelance-sniper-toggle`, `.freelance-error`, `.freelance-empty`, and `.freelance-order-note`. Preserve 44px minimum interactive targets, visible focus outlines, 150–300ms transitions, `prefers-reduced-motion`, and no document horizontal overflow at 375px, 768px, 1024px, and 1440px.

- [ ] **Step 5: Run TypeScript build and browser smoke checks.**

Run: `npm run build`

Expected: `tsc -b && vite build` exits 0.

Use the in-app browser to verify: empty API produces an empty page, manual order survives reload, status survives reload, filters work, source status errors do not hide saved orders, sniper start/stop changes state, and no console errors occur.

- [ ] **Step 6: Commit the frontend vertical slice.**

```powershell
git add src/pages/FreelancePage.tsx src/styles.css
git commit -m "feat: connect freelance page to API"
```

---

### Task 6: Local setup, live-source verification, and delivery QA

**Files:**
- Modify: `backend/README.md`
- Modify: `.env.example`
- Create: `backend/freelance/fixtures/README.md`

- [ ] **Step 1: Document safe local configuration and browser login.**

Document this exact template without real secrets:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_ID=800395558
FREELANCE_BROWSER_PROFILE=backend/data/freelance_browser
FREELANCE_POLL_INTERVAL_SECONDS=60
```

Document `pip install -r backend/requirements.txt`, `playwright install chromium`, backend/frontend start commands, and the manual login flow. State that the previously exposed bot token must be rotated before use.

- [ ] **Step 2: Verify fixtures and live adapters separately.**

Run: `py -3 -m unittest discover -s backend/tests -p "test_*.py" -v`

Expected: all fixture and repository tests pass without network access.

With the user’s local authorized browser profile, run one manual `POST /api/freelance/sniper/check` per enabled source. Record only source status, order count, and errors in the UI; do not commit captured personal pages, cookies, or production SQLite data.

- [ ] **Step 3: Verify frontend and accessibility behavior.**

Run: `npm run build` and `git diff --check`.

In the browser verify light/dark themes, keyboard focus in the settings modal, the empty state, one real/manual saved order, source errors, sniper toggle, no duplicate Telegram record after a second check, and `document.body.scrollWidth === document.documentElement.clientWidth` at desktop and mobile widths.

- [ ] **Step 4: Commit documentation and final changes.**

```powershell
git add backend/README.md .env.example backend/freelance/fixtures/README.md
git commit -m "docs: document freelance sniper setup"
```

- [ ] **Step 5: Final verification before claiming completion.**

Run:

```powershell
py -3 -m unittest discover -s backend/tests -p "test_*.py" -v
npm run build
git diff --check
git status --short
```

Expected: all tests pass, build exits 0, diff check has no errors, and only intentionally ignored runtime data exists outside Git.

## Plan Self-Review

- Spec coverage: source adapters, persistent orders, deduplication, scoring, statuses, filters, local Chromium sessions, Telegram recipient restriction, sniper lifecycle, API, UI, error isolation, fixtures, and browser QA each have explicit tasks.
- Placeholder scan: every implementation step contains a concrete file, interface, command, and expected result.
- Type consistency: `FreelanceOrder`, `FreelanceSettings`, `AdapterResult`, `TelegramNotifier`, `FreelanceSniper`, repository functions, and route names are defined before their consumers.
- Scope: financial accounting, automatic replies, cloud hosting, password storage, CAPTCHA bypass, and LLM reply generation remain explicitly out of scope.
