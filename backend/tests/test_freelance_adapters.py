from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.freelance.adapters.browser import ProfiAdapter, YoudoAdapter
from backend.freelance.adapters.public import FlAdapter, FreelanceRuAdapter, KworkAdapter
from backend.freelance.adapters.registry import adapter_registry, build_adapters
from backend.freelance.browser_profile import PersistentBrowserSession, browser_profile_path, persistent_browser_factory
from backend.freelance.models import AdapterResult, FreelanceOrder, FreelanceSettings


FIXTURES = Path(__file__).parent / "fixtures" / "freelance"


class FreelanceAdapterTests(unittest.TestCase):
    def test_fl_fixture_extracts_real_fields(self) -> None:
        html = (FIXTURES / "fl_projects.html").read_text(encoding="utf-8")
        result = FlAdapter().parse_html(html)
        self.assertEqual("fl", result[0].source)
        self.assertEqual("fl-100", result[0].external_id)
        self.assertEqual("React CRM для бизнеса", result[0].title)
        self.assertEqual("https://www.fl.ru/projects/100/", result[0].url)
        self.assertEqual(120000, result[0].budget_min)

    def test_kwork_fixture_extracts_embedded_state(self) -> None:
        html = (FIXTURES / "kwork_projects.html").read_text(encoding="utf-8")
        result = KworkAdapter().parse_html(html)
        self.assertEqual("kwork-3221147", result[0].external_id)
        self.assertEqual("https://kwork.ru/projects/3221147/view", result[0].url)
        self.assertEqual("varvaras3", result[0].customer)
        self.assertEqual(3000, result[0].budget_min)

    def test_public_adapter_retries_one_timeout(self) -> None:
        html = (FIXTURES / "kwork_projects.html").read_text(encoding="utf-8")

        class TimeoutThenSuccessKworkAdapter(KworkAdapter):
            def __init__(self):
                super().__init__(retry_delay=0, sleeper=lambda _delay: None)
                self.attempts = 0

            def fetch(self):
                self.attempts += 1
                if self.attempts == 1:
                    raise httpx.ReadTimeout("slow source")
                return html

        adapter = TimeoutThenSuccessKworkAdapter()
        result = adapter.collect(FreelanceSettings())
        self.assertEqual("done", result.status)
        self.assertEqual(2, adapter.attempts)

    def test_freelance_ru_fixture_extracts_task_card(self) -> None:
        html = (FIXTURES / "freelance_ru_projects.html").read_text(encoding="utf-8")
        result = FreelanceRuAdapter().parse_html(html)
        self.assertEqual("freelance_ru-5647", result[0].external_id)
        self.assertEqual("Создать сайт", result[0].title)
        self.assertEqual(100000, result[0].budget_min)
        self.assertEqual(("Веб-разработка и IT",), result[0].categories)

    def test_registry_contains_only_supported_sources(self) -> None:
        self.assertEqual(
            {"kwork", "fl", "freelance_ru", "profi", "youdo"},
            set(adapter_registry()),
        )

    def test_browser_adapter_reports_auth_required_without_session(self) -> None:
        result = ProfiAdapter(browser_factory=lambda: None).collect(FreelanceSettings())
        self.assertEqual("auth_required", result.status)
        self.assertTrue(result.auth_required)

    def test_browser_adapter_closes_persistent_session_after_check(self) -> None:
        class EmptyLocator:
            def all(self):
                return []

        class FakePage:
            url = "https://client.work-zilla.ru/freelancer"

            def goto(self, *_args, **_kwargs):
                return None

            def title(self):
                return "Заказы"

            def content(self):
                return "<main data-empty-state>Нет подходящих заказов</main>"

            def locator(self, _selector):
                return EmptyLocator()

        class FakeSession:
            def __init__(self):
                self.closed = False

            def new_page(self):
                return FakePage()

            def close(self):
                self.closed = True

        session = FakeSession()
        result = ProfiAdapter(browser_factory=lambda: session).collect(FreelanceSettings())
        self.assertEqual("empty", result.status)
        self.assertTrue(session.closed)

    def test_login_page_with_http_200_is_auth_required(self) -> None:
        class EmptyLocator:
            def all(self):
                return []

        class FakeResponse:
            status = 200

        class FakePage:
            url = "https://profi.ru/backoffice/a.php"

            def goto(self, *_args, **_kwargs):
                return FakeResponse()

            def title(self):
                return "Вход на Профи.ру"

            def content(self):
                return "<form><input type='password'></form>"

            def locator(self, _selector):
                return EmptyLocator()

        class FakeSession:
            def new_page(self):
                return FakePage()

            def close(self):
                return None

        result = ProfiAdapter(browser_factory=lambda: FakeSession()).collect(FreelanceSettings())
        self.assertEqual("auth_required", result.status)
        self.assertTrue(result.auth_required)

    def test_unknown_empty_markup_is_error(self) -> None:
        class EmptyLocator:
            def all(self):
                return []

        class FakeResponse:
            status = 200

        class FakePage:
            url = "https://profi.ru/backoffice/a.php"

            def goto(self, *_args, **_kwargs):
                return FakeResponse()

            def title(self):
                return "Профи"

            def content(self):
                return "<main></main>"

            def locator(self, _selector):
                return EmptyLocator()

        class FakeSession:
            def new_page(self):
                return FakePage()

            def close(self):
                return None

        result = ProfiAdapter(browser_factory=lambda: FakeSession()).collect(FreelanceSettings())
        self.assertEqual("error", result.status)

    def test_profi_fixture_extracts_order_fields(self) -> None:
        html = (FIXTURES / "profi_orders.html").read_text(encoding="utf-8")
        order = ProfiAdapter().parse_html(html, "https://profi.ru/backoffice/n.php")[0]
        self.assertEqual("profi", order.source)
        self.assertEqual("profi-12345", order.external_id)
        self.assertEqual("Разработка корпоративного сайта", order.title)
        self.assertEqual("https://profi.ru/backoffice/n.php?o=12345", order.url)
        self.assertEqual(5000, order.budget_min)
        self.assertEqual(("Разработка сайтов",), order.categories)

    def test_profi_confirmed_empty_fixture_is_empty(self) -> None:
        html = (FIXTURES / "profi_empty.html").read_text(encoding="utf-8")
        state = ProfiAdapter().classify_html(200, "Заказы", "https://profi.ru/backoffice/n.php", html)
        self.assertEqual("empty", state.status)

    def test_profi_feed_expansion_stops_after_five_stable_checks(self) -> None:
        class CountingLocator:
            def __init__(self):
                self.counts = iter((2, 4, 4, 4, 4, 4, 4))

            def count(self):
                return next(self.counts)

        class FakePage:
            def __init__(self):
                self.card_locator = CountingLocator()
                self.scrolls = 0

            def locator(self, selector):
                self.asserted_selector = selector
                return self.card_locator

            def evaluate(self, _script):
                self.scrolls += 1

            def wait_for_timeout(self, _timeout):
                return None

        page = FakePage()
        ProfiAdapter().prepare_page(page)
        self.assertEqual('[data-testid$="_order-snippet"]', page.asserted_selector)
        self.assertEqual(6, page.scrolls)

    def test_profi_feed_expansion_waits_through_delayed_growth(self) -> None:
        class CountingLocator:
            def __init__(self):
                self.values = iter((2, 2, 2, 2, 4, 4, 4, 4, 4, 4))
                self.seen = []

            def count(self):
                value = next(self.values)
                self.seen.append(value)
                return value

        class FakePage:
            def __init__(self):
                self.card_locator = CountingLocator()

            def locator(self, _selector):
                return self.card_locator

            def evaluate(self, _script):
                return None

            def wait_for_timeout(self, _timeout):
                return None

        page = FakePage()
        ProfiAdapter().prepare_page(page)
        self.assertIn(4, page.card_locator.seen)

    def test_youdo_403_is_blocked(self) -> None:
        state = YoudoAdapter().classify_html(403, "Доступ ограничен", "https://youdo.com/tasks-all-opened-all", "<main></main>")
        self.assertEqual("blocked", state.status)

    def test_youdo_script_markers_do_not_block_a_working_page(self) -> None:
        html = "<html><body><div>Задание по интеграции captcha challenge API</div><script src='/assets/challenge.js'>const challenge = 'captcha access denied';</script></body></html>"
        state = YoudoAdapter().classify_html(200, "Все задания", "https://youdo.com/tasks-all-opened-all", html)
        self.assertEqual("ready", state.status)

    def test_youdo_real_task_cards_override_access_words_in_task_text(self) -> None:
        html = '<ul><li class="TasksList_listItem__fixture"><a href="/t42">Исправить access denied</a></li></ul>'
        state = YoudoAdapter().classify_html(200, "Все задания", "https://youdo.com/tasks-all-opened-all", html)
        self.assertEqual("ready", state.status)

    def test_youdo_waits_for_react_tasks_before_classification(self) -> None:
        class FakeResponse:
            status = 200

        class FakePage:
            url = "https://youdo.com/tasks-all-opened-all"

            def __init__(self):
                self.ready = False

            def goto(self, *_args, **_kwargs):
                return FakeResponse()

            def title(self):
                return "Все задания"

            def content(self):
                if not self.ready:
                    return "<main>Доступ ограничен</main>"
                return '<ul><li class="TasksList_listItem__fixture"><a href="/t42">Рабочая задача</a></li></ul>'

        class FakeSession:
            def __init__(self):
                self.page = FakePage()

            def new_page(self):
                return self.page

            def close(self):
                return None

        class WaitingYoudoAdapter(YoudoAdapter):
            def wait_for_initial_state(self, page):
                page.ready = True

            def prepare_page(self, _page):
                return None

            def parse_page(self, _page):
                return [FreelanceOrder(source="youdo", external_id="youdo-42", title="Рабочая задача")]

        result = WaitingYoudoAdapter(browser_factory=lambda: FakeSession()).collect(FreelanceSettings())
        self.assertEqual("done", result.status)

    def test_youdo_retries_blocked_headless_once_in_headed_browser(self) -> None:
        class RecordingYoudoAdapter(YoudoAdapter):
            def __init__(self):
                super().__init__(browser_factory=lambda: None)
                self.headless_modes = []

            def _collect_once(self, settings, *, headless=True):
                self.headless_modes.append(headless)
                if headless:
                    return AdapterResult("youdo", "blocked", checked_at="now", error="HTTP 403")
                return AdapterResult("youdo", "done", checked_at="now")

        adapter = RecordingYoudoAdapter()
        result = adapter.collect(FreelanceSettings())
        self.assertEqual([True, False], adapter.headless_modes)
        self.assertEqual("done", result.status)

    def test_youdo_fixture_extracts_task_fields(self) -> None:
        html = (FIXTURES / "youdo_tasks.html").read_text(encoding="utf-8")
        order = YoudoAdapter().parse_html(html, "https://youdo.com/tasks-all-opened-all")[0]
        self.assertEqual("youdo", order.source)
        self.assertEqual("youdo-15001227", order.external_id)
        self.assertEqual("Разработать лендинг", order.title)
        self.assertEqual("https://youdo.com/t15001227", order.url)
        self.assertEqual(15000, order.budget_min)
        self.assertEqual(("Веб-разработка",), order.categories)

    def test_youdo_confirmed_empty_fixture_is_empty(self) -> None:
        html = (FIXTURES / "youdo_empty.html").read_text(encoding="utf-8")
        state = YoudoAdapter().classify_html(200, "Все задания", "https://youdo.com/tasks-all-opened-all", html)
        self.assertEqual("empty", state.status)

    def test_youdo_feed_expansion_stops_at_safety_limit(self) -> None:
        class TaskLocator:
            def __init__(self):
                self.value = 50

            def count(self):
                return self.value

        class ButtonLocator:
            def __init__(self, tasks):
                self.tasks = tasks
                self.first = self
                self.clicks = 0

            def count(self):
                return 1

            def is_visible(self):
                return True

            def click(self):
                self.clicks += 1
                self.tasks.value += 50

        class FakePage:
            def __init__(self):
                self.tasks = TaskLocator()
                self.button = ButtonLocator(self.tasks)

            def locator(self, selector):
                return self.button if "showMoreButton" in selector else self.tasks

            def wait_for_timeout(self, _timeout):
                return None

        page = FakePage()
        adapter = YoudoAdapter()
        adapter.max_tasks = 150
        adapter.prepare_page(page)
        self.assertEqual(2, page.button.clicks)
        self.assertEqual(150, page.tasks.value)

    def test_registry_injects_persistent_browser_factory_only_into_browser_sources(self) -> None:
        factory = lambda: None
        adapters = build_adapters(browser_factory=factory)
        self.assertIs(factory, adapters["profi"].browser_factory)
        self.assertIs(factory, adapters["youdo"].browser_factory)
        self.assertFalse(adapters["fl"].requires_browser)

    def test_persistent_session_prefers_detected_chrome_executable(self) -> None:
        class FakeContext:
            def close(self):
                return None

        class FakeChromium:
            def __init__(self):
                self.options = None

            def launch_persistent_context(self, **options):
                self.options = options
                return FakeContext()

        class FakePlaywright:
            def __init__(self):
                self.chromium = FakeChromium()

            def stop(self):
                return None

        fake_playwright = FakePlaywright()
        starter = type("Starter", (), {"start": lambda self: fake_playwright})()
        with patch("backend.freelance.browser_profile.sync_playwright", return_value=starter), patch(
            "backend.freelance.browser_profile.browser_profile_path", return_value=Path("C:/profile")
        ), patch(
            "backend.freelance.browser_profile.find_chrome_executable", return_value=Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
        ):
            session = PersistentBrowserSession()
            self.assertEqual("C:/Program Files/Google/Chrome/Application/chrome.exe", fake_playwright.chromium.options["executable_path"])
            self.assertNotIn("channel", fake_playwright.chromium.options)
            session.close()

    def test_missing_browser_runtime_returns_actionable_error(self) -> None:
        class FakeChromium:
            def launch_persistent_context(self, **_options):
                raise Exception("Executable doesn't exist at C:/missing/chrome.exe")

        class FakePlaywright:
            chromium = FakeChromium()

            def stop(self):
                return None

        fake_playwright = FakePlaywright()
        starter = type("Starter", (), {"start": lambda self: fake_playwright})()
        with patch("backend.freelance.browser_profile.sync_playwright", return_value=starter), patch(
            "backend.freelance.browser_profile.browser_profile_path", return_value=Path("C:/profile")
        ), patch("backend.freelance.browser_profile.find_chrome_executable", return_value=None), patch(
            "backend.freelance.browser_profile.browser_channel", return_value=None
        ):
            with self.assertRaisesRegex(RuntimeError, "playwright install chromium"):
                PersistentBrowserSession()

    def test_browser_profiles_are_isolated_per_source(self) -> None:
        with patch.dict("os.environ", {"FREELANCE_BROWSER_PROFILE": "C:/profiles"}), patch("pathlib.Path.mkdir"):
            self.assertNotEqual(browser_profile_path("youdo"), browser_profile_path("profi"))

    def test_busy_browser_profile_returns_close_window_message(self) -> None:
        class FakeChromium:
            def launch_persistent_context(self, **_options):
                raise Exception("BrowserType.launch_persistent_context: Target page, context or browser has been closed")

        class FakePlaywright:
            chromium = FakeChromium()

            def stop(self):
                return None

        fake_playwright = FakePlaywright()
        starter = type("Starter", (), {"start": lambda self: fake_playwright})()
        with patch("backend.freelance.browser_profile.sync_playwright", return_value=starter), patch(
            "backend.freelance.browser_profile.browser_profile_path", return_value=Path("C:/profile/profi")
        ), patch(
            "backend.freelance.browser_profile.find_chrome_executable", return_value=Path("C:/Chrome.exe")
        ):
            with self.assertRaisesRegex(RuntimeError, "Закройте окно входа Profi.ru"):
                PersistentBrowserSession(source="profi")

    def test_persistent_factory_passes_source_to_session(self) -> None:
        with patch("backend.freelance.browser_profile.PersistentBrowserSession") as session_type:
            persistent_browser_factory("youdo")
            session_type.assert_called_once_with(source="youdo", headless=True)

    def test_persistent_factory_forwards_headless_mode(self) -> None:
        with patch("backend.freelance.browser_profile.PersistentBrowserSession") as session_type:
            persistent_browser_factory("youdo", headless=False)
            session_type.assert_called_once_with(source="youdo", headless=False)

    def test_headed_persistent_session_starts_minimized(self) -> None:
        class FakeContext:
            def close(self):
                return None

        class FakeChromium:
            def __init__(self):
                self.options = None

            def launch_persistent_context(self, **options):
                self.options = options
                return FakeContext()

        class FakePlaywright:
            def __init__(self):
                self.chromium = FakeChromium()

            def stop(self):
                return None

        fake_playwright = FakePlaywright()
        starter = type("Starter", (), {"start": lambda self: fake_playwright})()
        with patch("backend.freelance.browser_profile.sync_playwright", return_value=starter), patch(
            "backend.freelance.browser_profile.browser_profile_path", return_value=Path("C:/profile/youdo")
        ), patch(
            "backend.freelance.browser_profile.find_chrome_executable", return_value=Path("C:/Chrome.exe")
        ):
            session = PersistentBrowserSession(source="youdo", headless=False)
            self.assertIn("--start-minimized", fake_playwright.chromium.options["args"])
            session.close()


if __name__ == "__main__":
    unittest.main()
