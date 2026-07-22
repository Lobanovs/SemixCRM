from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database


class ScheduleDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "schedule.sqlite3"
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_schedule_stores_tasks_notes_summary_and_goals(self) -> None:
        task = database.create_schedule_task("2026-07-20", "Позвонить клиенту", "10:30", "meeting")
        self.assertEqual("Позвонить клиенту", task["title"])
        self.assertFalse(task["done"])
        self.assertEqual("meeting", task["kind"])

        database.save_schedule_note("2026-07-20", "Созвон состоялся")
        database.save_schedule_week(
            "2026-07-20",
            "Неделя с фокусом на клиентах",
            [{"title": "Сделать 3 созвона", "done": False}],
        )

        payload = database.get_schedule("2026-07-20")
        self.assertEqual(1, payload["stats"]["total"])
        self.assertEqual(1, payload["stats"]["meetings"])
        self.assertEqual("Созвон состоялся", payload["notes"]["2026-07-20"])
        self.assertEqual("Неделя с фокусом на клиентах", payload["summary"])
        self.assertEqual("Сделать 3 созвона", payload["goals"][0]["title"])

    def test_task_completion_updates_persisted_statistics(self) -> None:
        task = database.create_schedule_task("2026-07-21", "Подготовить отчёт")
        updated = database.update_schedule_task(int(task["id"]), done=True)

        self.assertIsNotNone(updated)
        self.assertTrue(updated["done"])
        payload = database.get_schedule("2026-07-20")
        self.assertEqual(1, payload["stats"]["done"])
        self.assertEqual(100, payload["stats"]["completion_percent"])

    def test_task_fields_can_be_edited_and_task_can_be_deleted(self) -> None:
        task = database.create_schedule_task("2026-07-20", "Черновик")

        updated = database.update_schedule_task(
            int(task["id"]),
            title="Готовая задача",
            task_date="2026-07-21",
            task_time="14:30",
            kind="meeting",
            done=True,
        )

        self.assertIsNotNone(updated)
        self.assertEqual("Готовая задача", updated["title"])
        self.assertEqual("2026-07-21", updated["date"])
        self.assertEqual("14:30", updated["time"])
        self.assertEqual("meeting", updated["kind"])
        self.assertTrue(updated["done"])
        self.assertTrue(database.delete_schedule_task(int(task["id"])))
        self.assertEqual([], database.get_schedule("2026-07-20")["tasks"])
        self.assertFalse(database.delete_schedule_task(int(task["id"])))

    def test_empty_schedule_has_no_seeded_or_fake_records(self) -> None:
        payload = database.get_schedule("2026-07-20")

        self.assertEqual([], payload["tasks"])
        self.assertEqual({}, payload["notes"])
        self.assertEqual([], payload["goals"])
        self.assertEqual(0, payload["stats"]["total"])
        self.assertEqual([], payload["upcoming"])


if __name__ == "__main__":
    unittest.main()
