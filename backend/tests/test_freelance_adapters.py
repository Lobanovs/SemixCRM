from __future__ import annotations

import unittest
from pathlib import Path

from backend.freelance.adapters.browser import WorkzillaAdapter
from backend.freelance.adapters.public import FlAdapter
from backend.freelance.adapters.registry import adapter_registry
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

    def test_registry_contains_all_requested_sources(self) -> None:
        self.assertEqual(
            {"kwork", "fl", "freelance_ru", "workzilla", "freelancehunt", "profi", "youdo"},
            set(adapter_registry()),
        )

    def test_browser_adapter_reports_auth_required_without_session(self) -> None:
        result = WorkzillaAdapter(browser_factory=lambda: None).collect(FreelanceSettings())
        self.assertEqual("auth_required", result.status)
        self.assertTrue(result.auth_required)


if __name__ == "__main__":
    unittest.main()
