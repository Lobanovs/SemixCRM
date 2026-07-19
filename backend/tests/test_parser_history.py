from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database


class ParserHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def _lead(self, name: str = "Studio Forma") -> dict[str, object]:
        return {
            "name": name,
            "source": "2gis",
            "city": "Moscow",
            "niche": "beauty salons",
            "address": "1 Main street",
            "phone": "+79990000000",
            "website": "",
            "rating": 4.8,
            "reviews": 42,
            "card_url": "https://2gis.ru/card/studio-forma",
            "contacts": [{"type": "telegram", "label": "Telegram", "value": "@studio_forma", "url": "https://t.me/studio_forma"}],
        }

    def test_archive_list_and_restore(self) -> None:
        result = database.insert_clients([self._lead()])
        client_id = int(result["inserted_ids"][0])

        self.assertTrue(database.archive_client(client_id))
        self.assertEqual([], database.list_clients())
        archived = database.list_archived_clients()
        self.assertEqual([client_id], [item["id"] for item in archived])
        self.assertEqual(1, archived[0]["archived"])
        self.assertTrue(archived[0]["archived_at"])

        restored = database.restore_client(client_id)
        self.assertIsNotNone(restored)
        self.assertEqual(0, restored["archived"])
        self.assertEqual(client_id, database.list_clients()[0]["id"])

    def test_run_snapshot_keeps_inserted_and_duplicate_in_order(self) -> None:
        database.create_parser_run("run-1", "Moscow", "beauty salons", "2gis", 10)
        first = self._lead()
        result = database.insert_clients([first, dict(first)])

        self.assertEqual(2, len(result["results"]))
        self.assertEqual(["inserted", "duplicate"], [item["outcome"] for item in result["results"]])
        self.assertEqual(result["results"][0]["client_id"], result["results"][1]["client_id"])

        database.save_parser_run_results("run-1", result["results"])
        database.update_parser_run("run-1", "done", result["inserted_count"], "done", skipped_count=result["duplicate_count"], parsed_count=2)
        detail = database.get_parser_run("run-1")

        self.assertIsNotNone(detail)
        self.assertTrue(detail["snapshot_available"])
        self.assertEqual(2, detail["parsed_count"])
        self.assertEqual(["inserted", "duplicate"], [item["outcome"] for item in detail["results"]])
        self.assertEqual("Studio Forma", detail["results"][0]["snapshot"]["name"])
        self.assertEqual(42, detail["results"][0]["snapshot"]["reviews"])

    def test_legacy_run_is_explicitly_marked_without_snapshot(self) -> None:
        database.create_parser_run("legacy", "Moscow", "beauty salons", "2gis", 10)
        detail = database.get_parser_run("legacy")

        self.assertIsNotNone(detail)
        self.assertFalse(detail["snapshot_available"])
        self.assertEqual([], detail["results"])


if __name__ == "__main__":
    unittest.main()
