from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database
from backend.freelance.models import FreelanceOrder, FreelanceOrderFilters, FreelanceSettings
from backend.freelance.scoring import score_order


class FreelanceOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "freelance.sqlite3"
        self.path_patch = patch.object(database, "DB_PATH", self.db_path)
        self.path_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_order_is_persisted_and_duplicate_external_id_is_rejected(self) -> None:
        order = FreelanceOrder(source="fl", external_id="fl-42", title="React CRM", url="https://fl.ru/projects/42")
        first = database.create_freelance_order(order)
        second = database.create_freelance_order(order)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(1, len(database.list_freelance_orders(FreelanceOrderFilters())))

    def test_filters_and_stats_use_only_saved_orders(self) -> None:
        database.create_freelance_order(FreelanceOrder(source="kwork", external_id="1", title="React site", budget_min=70000, status="Новый"))
        database.create_freelance_order(FreelanceOrder(source="fl", external_id="2", title="Copywriting", budget_min=10000, status="В работе"))
        result = database.list_freelance_orders(FreelanceOrderFilters(source="kwork", min_budget=50000))
        self.assertEqual(["React site"], [item["title"] for item in result])
        self.assertEqual(2, database.freelance_stats()["total"])

    def test_score_explains_keyword_and_budget_matches(self) -> None:
        order = FreelanceOrder(source="fl", external_id="3", title="Next.js CRM", description="Нужен сайт", budget_min=120000)
        settings = FreelanceSettings(keywords=["CRM", "Next.js"], min_budget=50000)
        score, reasons = score_order(order, settings)
        self.assertGreaterEqual(score, 70)
        self.assertIn("Совпадение ключевого слова в названии", " ".join(reasons))

    def test_empty_database_has_no_seed_orders(self) -> None:
        self.assertEqual([], database.list_freelance_orders(FreelanceOrderFilters()))
        self.assertEqual(0, database.freelance_stats()["total"])


if __name__ == "__main__":
    unittest.main()
