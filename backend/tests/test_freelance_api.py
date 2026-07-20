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
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
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

    def test_sniper_controls_are_idempotent(self) -> None:
        self.assertEqual("running", self.client.post("/api/freelance/sniper/start").json()["status"])
        self.assertEqual("running", self.client.post("/api/freelance/sniper/start").json()["status"])
        self.assertEqual("stopped", self.client.post("/api/freelance/sniper/stop").json()["status"])


if __name__ == "__main__":
    unittest.main()
