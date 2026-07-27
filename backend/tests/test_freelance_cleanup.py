from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from backend.freelance.models import FreelanceCleanupRules, FreelanceOrder, FreelanceOrderFilters
from backend.main import app


def days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class FreelanceCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "cleanup.sqlite3")
        self.path_patch.start()
        database.init_db()
        self._seed()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def _seed(self) -> None:
        self.fresh_good = database.create_freelance_order(FreelanceOrder(
            source="kwork", external_id="a", title="Разработка сайта на React",
            relevance=80, relevance_points=16, discovered_at=days_ago(0),
        ))
        self.old_good = database.create_freelance_order(FreelanceOrder(
            source="fl", external_id="b", title="Телеграм-бот для записи",
            relevance=75, relevance_points=15, discovered_at=days_ago(10),
        ))
        self.fresh_weak = database.create_freelance_order(FreelanceOrder(
            source="youdo", external_id="c", title="Помощь с документами",
            relevance=10, relevance_points=2, discovered_at=days_ago(0),
        ))
        self.old_weak = database.create_freelance_order(FreelanceOrder(
            source="youdo", external_id="d", title="Собрать мебель",
            relevance=0, relevance_points=0, discovered_at=days_ago(20),
        ))
        # Заказ, по которому уже идёт переписка — его уборка трогать не должна.
        worked = database.create_freelance_order(FreelanceOrder(
            source="kwork", external_id="e", title="Лендинг для клиники",
            relevance=5, relevance_points=1, discovered_at=days_ago(30),
        ))
        database.update_freelance_order(worked["id"], status="Написал")
        self.worked_id = worked["id"]

    def active_titles(self) -> list[str]:
        return [item["title"] for item in database.list_freelance_orders(FreelanceOrderFilters())]

    def test_empty_rules_hide_nothing(self) -> None:
        self.assertEqual(0, database.cleanup_freelance_orders(FreelanceCleanupRules()))
        self.assertEqual(5, len(self.active_titles()))

    def test_relevance_rule_hides_only_weak_orders(self) -> None:
        hidden = database.cleanup_freelance_orders(FreelanceCleanupRules(max_relevance=40))

        self.assertEqual(2, hidden)
        self.assertEqual(
            {"Разработка сайта на React", "Телеграм-бот для записи", "Лендинг для клиники"},
            set(self.active_titles()),
        )

    def test_age_rule_hides_only_old_orders(self) -> None:
        hidden = database.cleanup_freelance_orders(FreelanceCleanupRules(older_than_days=7))

        self.assertEqual(2, hidden)
        self.assertEqual(
            {"Разработка сайта на React", "Помощь с документами", "Лендинг для клиники"},
            set(self.active_titles()),
        )

    def test_rules_combine_as_and(self) -> None:
        hidden = database.cleanup_freelance_orders(FreelanceCleanupRules(older_than_days=7, max_relevance=40))

        self.assertEqual(1, hidden)
        self.assertNotIn("Собрать мебель", self.active_titles())

    def test_worked_orders_survive_even_a_full_wipe(self) -> None:
        hidden = database.cleanup_freelance_orders(FreelanceCleanupRules(include_everything=True))

        self.assertEqual(4, hidden)
        self.assertEqual(["Лендинг для клиники"], self.active_titles())

    def test_worked_orders_can_be_wiped_when_safety_is_off(self) -> None:
        hidden = database.cleanup_freelance_orders(
            FreelanceCleanupRules(include_everything=True, keep_worked=False)
        )

        self.assertEqual(5, hidden)
        self.assertEqual([], self.active_titles())

    def test_source_rule_limits_the_sweep(self) -> None:
        hidden = database.cleanup_freelance_orders(FreelanceCleanupRules(sources=("youdo",)))

        self.assertEqual(2, hidden)
        self.assertNotIn("Помощь с документами", self.active_titles())
        self.assertIn("Разработка сайта на React", self.active_titles())

    def test_preview_counts_without_touching_anything(self) -> None:
        preview = database.preview_freelance_cleanup(FreelanceCleanupRules(max_relevance=40))

        self.assertEqual(2, preview["matched"])
        self.assertEqual(3, preview["kept"])
        self.assertEqual(5, len(self.active_titles()), "предпросмотр не должен ничего скрывать")

    def test_preview_shows_the_weakest_orders_first(self) -> None:
        preview = database.preview_freelance_cleanup(FreelanceCleanupRules(max_relevance=40))

        self.assertEqual("Собрать мебель", preview["sample"][0]["title"])
        self.assertEqual(0, preview["sample"][0]["relevance"])

    def test_restore_all_brings_everything_back(self) -> None:
        database.cleanup_freelance_orders(FreelanceCleanupRules(include_everything=True))
        self.assertEqual(1, len(self.active_titles()))

        restored = database.restore_all_freelance_orders()

        self.assertEqual(4, restored)
        self.assertEqual(5, len(self.active_titles()))

    def test_hidden_orders_are_archived_not_deleted(self) -> None:
        database.cleanup_freelance_orders(FreelanceCleanupRules(max_relevance=40))

        archived = database.list_freelance_orders(FreelanceOrderFilters(include_archived=True))

        self.assertEqual(2, len(archived))
        self.assertEqual(2, database.freelance_stats()["archived"])


class FreelanceCleanupApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "api.sqlite3")
        self.path_patch.start()
        self.registry_patch = patch("backend.main.build_adapters", return_value={})
        self.registry_patch.start()
        self.client_context = TestClient(app, headers={"X-Requested-With": "SemixCRM"})
        self.client = self.client_context.__enter__()
        for index in range(4):
            self.client.post("/api/freelance/orders", json={
                "source": "kwork", "external_id": f"api-{index}", "title": f"Заказ {index}",
                "url": f"https://kwork.ru/projects/{index}",
            })

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.registry_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_preview_returns_a_count_and_changes_nothing(self) -> None:
        response = self.client.post("/api/freelance/orders/cleanup", json={"include_everything": True, "preview": True})

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["preview"])
        self.assertEqual(4, response.json()["matched"])
        self.assertEqual(4, self.client.get("/api/freelance/orders").json()["stats"]["total"])

    def test_apply_hides_orders_and_returns_fresh_stats(self) -> None:
        response = self.client.post("/api/freelance/orders/cleanup", json={"include_everything": True})

        self.assertEqual(4, response.json()["archived_count"])
        self.assertEqual(0, response.json()["stats"]["total"])
        self.assertEqual(4, response.json()["stats"]["archived"])

    def test_restore_all_endpoint_brings_orders_back(self) -> None:
        self.client.post("/api/freelance/orders/cleanup", json={"include_everything": True})

        restored = self.client.post("/api/freelance/orders/restore-all")

        self.assertEqual(4, restored.json()["restored_count"])
        self.assertEqual(4, restored.json()["stats"]["total"])

    def test_unknown_source_is_rejected(self) -> None:
        response = self.client.post("/api/freelance/orders/cleanup", json={"sources": ["superjob"]})

        self.assertEqual(422, response.status_code)

    def test_unknown_status_is_rejected(self) -> None:
        response = self.client.post("/api/freelance/orders/cleanup", json={"statuses": ["Придумал"]})

        self.assertEqual(422, response.status_code)

    def test_cleanup_requires_the_protective_header(self) -> None:
        with TestClient(app) as bare_client:
            self.assertEqual(403, bare_client.post("/api/freelance/orders/cleanup", json={"include_everything": True}).status_code)
            self.assertEqual(403, bare_client.post("/api/freelance/orders/restore-all").status_code)

    def test_cleanup_route_is_not_shadowed_by_the_id_route(self) -> None:
        response = self.client.post("/api/freelance/orders/cleanup", json={"preview": True})

        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.json()["matched"])


if __name__ == "__main__":
    unittest.main()
