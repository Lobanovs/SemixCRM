from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.freelance.adapters.browser import ProfiAdapter
from backend.freelance.adapters.public import FlAdapter, FreelanceRuAdapter, KworkAdapter
from backend.freelance.adapters.registry import adapter_registry, build_adapters
from backend.freelance.browser_profile import PersistentBrowserSession, browser_profile_path, persistent_browser_factory
from backend.freelance.models import FreelanceSettings


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
            self.assertNotEqual(browser_profile_path("workzilla"), browser_profile_path("profi"))

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
