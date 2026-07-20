from __future__ import annotations

import unittest
import json
from pathlib import Path

from backend.freelance.adapters.browser import WorkzillaAdapter
from backend.freelance.adapters.public import FlAdapter, FreelanceRuAdapter, FreelancehuntAdapter, KworkAdapter
from backend.freelance.adapters.registry import adapter_registry, build_adapters
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

    def test_freelancehunt_fixture_extracts_api_project(self) -> None:
        payload = json.loads((FIXTURES / "freelancehunt_projects.json").read_text(encoding="utf-8"))
        result = FreelancehuntAdapter(token="test-token").parse_json(payload)
        self.assertEqual("1493532", result[0].external_id)
        self.assertEqual("https://freelancehunt.com/project/1493532.html", result[0].url)
        self.assertEqual(91000, result[0].budget_min)

    def test_freelancehunt_requires_api_token(self) -> None:
        result = FreelancehuntAdapter(token="").collect(FreelanceSettings())
        self.assertEqual("auth_required", result.status)
        self.assertTrue(result.auth_required)

    def test_registry_contains_all_requested_sources(self) -> None:
        self.assertEqual(
            {"kwork", "fl", "freelance_ru", "workzilla", "freelancehunt", "profi", "youdo"},
            set(adapter_registry()),
        )

    def test_browser_adapter_reports_auth_required_without_session(self) -> None:
        result = WorkzillaAdapter(browser_factory=lambda: None).collect(FreelanceSettings())
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
        result = WorkzillaAdapter(browser_factory=lambda: session).collect(FreelanceSettings())
        self.assertEqual("empty", result.status)
        self.assertTrue(session.closed)

    def test_registry_injects_persistent_browser_factory_only_into_browser_sources(self) -> None:
        factory = lambda: None
        adapters = build_adapters(browser_factory=factory)
        self.assertIs(factory, adapters["workzilla"].browser_factory)
        self.assertIs(factory, adapters["profi"].browser_factory)
        self.assertIs(factory, adapters["youdo"].browser_factory)
        self.assertFalse(adapters["fl"].requires_browser)


if __name__ == "__main__":
    unittest.main()
