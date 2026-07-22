from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from backend.main import app


class ScheduleApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "schedule-api.sqlite3"
        self.path_patch = patch.object(database, "DB_PATH", self.db_path)
        self.path_patch.start()
        self.registry_patch = patch("backend.main.build_adapters", return_value={})
        self.registry_patch.start()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.registry_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_task_crud_round_trip(self) -> None:
        created = self.client.post(
            "/api/schedule/tasks",
            json={"task_date": "2026-07-20", "title": "Черновик", "task_time": "", "kind": "task"},
        )
        self.assertEqual(200, created.status_code)
        task_id = created.json()["id"]

        updated = self.client.put(
            f"/api/schedule/tasks/{task_id}",
            json={"title": "Созвон", "task_date": "2026-07-21", "task_time": "15:00", "kind": "meeting"},
        )
        self.assertEqual(200, updated.status_code)
        self.assertEqual("Созвон", updated.json()["title"])
        self.assertEqual("2026-07-21", updated.json()["date"])
        self.assertEqual("15:00", updated.json()["time"])
        self.assertEqual("meeting", updated.json()["kind"])

        deleted = self.client.delete(f"/api/schedule/tasks/{task_id}")
        self.assertEqual(200, deleted.status_code)
        self.assertEqual({"ok": True, "deleted_id": task_id}, deleted.json())
        self.assertEqual([], self.client.get("/api/schedule?week_start=2026-07-20").json()["tasks"])

    def test_missing_task_update_and_delete_return_404(self) -> None:
        updated = self.client.put("/api/schedule/tasks/999", json={"title": "Нет задачи"})
        deleted = self.client.delete("/api/schedule/tasks/999")

        self.assertEqual(404, updated.status_code)
        self.assertEqual("Задача не найдена", updated.json()["detail"])
        self.assertEqual(404, deleted.status_code)
        self.assertEqual("Задача не найдена", deleted.json()["detail"])


if __name__ == "__main__":
    unittest.main()
