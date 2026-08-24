from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import dashboard, main


NOW = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)


class DashboardBuilderTests(unittest.TestCase):
    def test_builds_bounded_action_queues_and_stats(self) -> None:
        clients = [
            {"id": index, "name": f"Клиент {index}", "niche": "Клиника", "city": "Москва", "status": "Новый",
             "lead_score": 100 - index, "lead_score_max": 100, "reviews": index, "rating": 4.8, "phone": "+7000"}
            for index in range(1, 9)
        ] + [{"id": 99, "name": "Уже написали", "status": "Написал", "lead_score": 100}]
        jobs = [
            {"id": index, "role": f"React {index}", "company": "Acme", "source": "habr", "status": "Сохранено",
             "relevance": 100 - index, "salary_text": "200 000 ₽", "discovered_at": "2026-08-24T08:00:00+00:00"}
            for index in range(1, 9)
        ]
        freelance = [
            {"id": index, "title": f"Заказ {index}", "source": "kwork", "status": "Новый", "relevance": 90 - index,
             "budget_text": "50 000 ₽", "published_at": "2026-08-24T07:00:00+00:00"}
            for index in range(1, 8)
        ]
        schedule = {
            "tasks": [
                {"id": 1, "title": "Позвонить", "date": "2026-08-24", "time": "12:00", "kind": "task", "done": False},
                {"id": 2, "title": "Готово", "date": "2026-08-24", "time": "09:00", "kind": "task", "done": True},
            ],
            "stats": {"total": 2, "done": 1},
        }

        with (
            patch.object(dashboard.database, "list_clients", return_value=clients),
            patch.object(dashboard.database, "client_stats", return_value={"total": 9, "stages": {"Новый": 8}}),
            patch.object(dashboard.database, "get_schedule", return_value=schedule),
            patch.object(dashboard.database, "list_freelance_orders", return_value=freelance),
            patch.object(dashboard.database, "freelance_stats", return_value={"total": 7}),
            patch.object(dashboard.database, "list_source_statuses", return_value=[]),
            patch.object(dashboard.jobs_storage, "list_jobs", return_value=jobs),
            patch.object(dashboard.jobs_storage, "job_stats", return_value={"total": 8, "stages": {"Сохранено": 8}}),
            patch.object(dashboard.jobs_storage, "list_job_source_statuses", return_value=[]),
        ):
            payload = dashboard.build_dashboard(now=NOW, limit=5)

        self.assertEqual(9, payload["stats"]["clients_total"])
        self.assertEqual(8, payload["stats"]["clients_to_contact"])
        self.assertEqual(1, payload["stats"]["tasks_open"])
        self.assertEqual(8, payload["stats"]["jobs_new"])
        self.assertEqual(7, payload["stats"]["freelance_active"])
        self.assertEqual(5, len(payload["clients"]))
        self.assertEqual([1, 2, 3, 4, 5], [item["id"] for item in payload["clients"]])
        self.assertEqual(5, len(payload["jobs"]))
        self.assertEqual(5, len(payload["freelance"]))
        self.assertEqual([1], [item["id"] for item in payload["tasks"]])

    def test_marks_failed_stale_and_never_checked_sources_for_attention(self) -> None:
        with (
            patch.object(dashboard.database, "list_clients", return_value=[]),
            patch.object(dashboard.database, "client_stats", return_value={"total": 0, "stages": {}}),
            patch.object(dashboard.database, "get_schedule", return_value={"tasks": [], "stats": {}}),
            patch.object(dashboard.database, "list_freelance_orders", return_value=[]),
            patch.object(dashboard.database, "freelance_stats", return_value={"total": 0}),
            patch.object(dashboard.database, "list_source_statuses", return_value=[
                {"source": "kwork", "status": "error", "checked_at": "2026-08-24T09:00:00+00:00", "error": "Сеть"},
                {"source": "profi", "status": "done", "checked_at": "2026-08-20T09:00:00+00:00", "error": ""},
            ]),
            patch.object(dashboard.jobs_storage, "list_jobs", return_value=[]),
            patch.object(dashboard.jobs_storage, "job_stats", return_value={"total": 0, "stages": {}}),
            patch.object(dashboard.jobs_storage, "list_job_source_statuses", return_value=[
                {"source": "habr", "status": "done", "checked_at": "2026-08-24T09:00:00+00:00", "error": ""},
            ]),
        ):
            payload = dashboard.build_dashboard(now=NOW, limit=5)

        health = {(item["kind"], item["source"]): item for item in payload["source_health"]}
        self.assertTrue(health[("freelance", "kwork")]["needs_attention"])
        self.assertEqual("error", health[("freelance", "kwork")]["state"])
        self.assertTrue(health[("freelance", "profi")]["is_stale"])
        self.assertEqual("stale", health[("freelance", "profi")]["state"])
        self.assertFalse(health[("jobs", "habr")]["needs_attention"])
        self.assertEqual("healthy", health[("jobs", "habr")]["state"])
        self.assertEqual("never", health[("jobs", "hh")]["state"])


class DashboardApiTests(unittest.TestCase):
    def test_dashboard_route_forwards_bounded_limit(self) -> None:
        expected = {"stats": {}, "clients": [], "tasks": [], "jobs": [], "freelance": [], "source_health": []}
        with patch.object(main, "build_dashboard", return_value=expected) as builder:
            response = TestClient(main.app).get("/api/dashboard?limit=7")

        self.assertEqual(200, response.status_code)
        self.assertEqual(expected, response.json())
        builder.assert_called_once_with(limit=7)

    def test_dashboard_route_rejects_unbounded_limit(self) -> None:
        response = TestClient(main.app).get("/api/dashboard?limit=100")
        self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
