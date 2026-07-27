from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from backend.main import app


class FreelanceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "freelance.sqlite3"
        self.path_patch = patch.object(database, "DB_PATH", self.db_path)
        self.path_patch.start()
        self.registry_patch = patch("backend.main.build_adapters", return_value={})
        self.registry_patch.start()
        # Тот же заголовок шлёт фронтенд: без него защищённые маршруты отвечают 403.
        self.client_context = TestClient(app, headers={"X-Requested-With": "SemixCRM"})
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.registry_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_orders_endpoint_is_empty_without_seed_data(self) -> None:
        response = self.client.get("/api/freelance/orders")
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json()["orders"])

    def test_create_and_update_order_round_trip(self) -> None:
        created = self.client.post("/api/freelance/orders", json={"source": "manual", "title": "Новый лендинг", "url": "https://example.test/order"})
        self.assertEqual(201, created.status_code)
        order_id = created.json()["id"]
        updated = self.client.put(f"/api/freelance/orders/{order_id}", json={"status": "Написал", "next_step": "Жду ответа", "note": "Проверить завтра"})
        self.assertEqual(200, updated.status_code)
        self.assertEqual("Написал", updated.json()["status"])

    def test_archived_query_lists_hidden_orders_and_put_restores_them(self) -> None:
        created = self.client.post("/api/freelance/orders", json={"source": "manual", "title": "Archived order"})
        order_id = created.json()["id"]
        self.assertEqual(200, self.client.delete(f"/api/freelance/orders/{order_id}").status_code)
        hidden = self.client.get("/api/freelance/orders?archived=true")
        self.assertEqual(200, hidden.status_code)
        self.assertEqual(["Archived order"], [item["title"] for item in hidden.json()["orders"]])
        restored = self.client.put(f"/api/freelance/orders/{order_id}", json={"archived": False})
        self.assertEqual(200, restored.status_code)
        self.assertFalse(restored.json()["archived"])
        self.assertEqual([], self.client.get("/api/freelance/orders?archived=true").json()["orders"])

    def test_sniper_controls_are_idempotent(self) -> None:
        self.assertEqual("running", self.client.post("/api/freelance/sniper/start").json()["status"])
        self.assertEqual("running", self.client.post("/api/freelance/sniper/start").json()["status"])
        self.assertEqual("stopped", self.client.post("/api/freelance/sniper/stop").json()["status"])

    def test_saving_enabled_setting_starts_sniper_and_disabling_stops_it(self) -> None:
        payload = {
            "sources": ["fl"],
            "keywords": [],
            "excluded_keywords": [],
            "categories": [],
            "min_budget": 0,
            "interval_seconds": 60,
            "telegram_enabled": False,
            "sniper_enabled": True,
        }
        enabled = self.client.put("/api/freelance/settings", json=payload)
        self.assertEqual(200, enabled.status_code)
        self.assertEqual("running", self.client.get("/api/freelance/sniper/status").json()["status"])
        payload["sniper_enabled"] = False
        disabled = self.client.put("/api/freelance/settings", json=payload)
        self.assertEqual(200, disabled.status_code)
        self.assertEqual("stopped", self.client.get("/api/freelance/sniper/status").json()["status"])

    @patch("backend.main.open_login_window")
    def test_browser_source_auth_opens_local_profile(self, open_login_window) -> None:
        open_login_window.return_value = {"source": "profi", "status": "opened", "pid": 42}
        response = self.client.post("/api/freelance/sources/profi/auth")
        self.assertEqual(200, response.status_code)
        self.assertEqual("opened", response.json()["status"])
        open_login_window.assert_called_once_with("profi")

    def test_workzilla_auth_endpoint_is_removed(self) -> None:
        response = self.client.post("/api/freelance/sources/workzilla/auth")
        self.assertEqual(404, response.status_code)

    def test_public_source_does_not_offer_browser_auth(self) -> None:
        response = self.client.post("/api/freelance/sources/fl/auth")
        self.assertEqual(422, response.status_code)

    def test_run_history_endpoint_returns_saved_run_and_orders(self) -> None:
        response = self.client.post("/api/freelance/sniper/check")
        self.assertEqual(200, response.status_code)
        runs = self.client.get("/api/freelance/runs")
        self.assertEqual(200, runs.status_code)
        self.assertEqual(1, len(runs.json()["runs"]))
        detail = self.client.get(f"/api/freelance/runs/{runs.json()['runs'][0]['id']}")
        self.assertEqual(200, detail.status_code)
        self.assertEqual([], detail.json()["orders"])


if __name__ == "__main__":
    unittest.main()
