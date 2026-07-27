from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database
from backend.freelance.models import FreelanceOrder, FreelanceOrderFilters, FreelanceSettings
from backend.freelance.scoring import FREELANCE_SCORE_MAX, score_order


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

    def test_score_explains_profile_stack_and_budget(self) -> None:
        order = FreelanceOrder(source="fl", external_id="3", title="Next.js CRM", description="Нужен сайт", budget_min=120000)
        settings = FreelanceSettings(keywords=["CRM", "Next.js"], min_budget=50000)

        points, reasons, percent = score_order(order, settings)

        self.assertGreaterEqual(percent, 70)
        joined = " ".join(reasons)
        self.assertIn("Профильная задача в названии", joined)
        self.assertIn("Знакомый стек", joined)
        self.assertIn("Бюджет от", joined)
        self.assertEqual(round(points / FREELANCE_SCORE_MAX * 100), percent)

    def test_off_profile_order_is_zeroed(self) -> None:
        # Курьерская доставка не должна конкурировать с разработкой в списке.
        order = FreelanceOrder(source="youdo", external_id="4", title="Курьер доставить документы", budget_min=90000)

        points, reasons, percent = score_order(order, FreelanceSettings())

        self.assertEqual(0, points)
        self.assertEqual(0, percent)
        self.assertIn("Не ваш профиль", reasons[0])

    def test_development_order_outranks_vague_one(self) -> None:
        settings = FreelanceSettings()
        strong = FreelanceOrder(source="fl", external_id="5", title="Доработать телеграм-бот на aiogram", budget_min=60000, customer="ООО Ромашка")
        weak = FreelanceOrder(source="fl", external_id="6", title="Нужна помощь по проекту")

        self.assertGreater(score_order(strong, settings)[0], score_order(weak, settings)[0])

    def test_tiny_budget_lowers_the_score(self) -> None:
        settings = FreelanceSettings()
        cheap = FreelanceOrder(source="kwork", external_id="7", title="Сделать лендинг на Tilda", budget_min=1500)
        fair = FreelanceOrder(source="kwork", external_id="8", title="Сделать лендинг на Tilda", budget_min=45000)

        cheap_points, cheap_reasons, _ = score_order(cheap, settings)
        fair_points, _, _ = score_order(fair, settings)

        self.assertLess(cheap_points, fair_points)
        self.assertIn("не окупается", " ".join(cheap_reasons))

    def test_points_are_stored_alongside_the_percentage(self) -> None:
        order = FreelanceOrder(
            source="fl", external_id="9", title="Разработка сайта на React",
            relevance=85, relevance_points=17, relevance_reasons=("Профильная задача",),
        )

        stored = database.create_freelance_order(order)

        self.assertEqual(85, stored["relevance"])
        self.assertEqual(17, stored["relevance_points"])

    def test_empty_database_has_no_seed_orders(self) -> None:
        self.assertEqual([], database.list_freelance_orders(FreelanceOrderFilters()))
        self.assertEqual(0, database.freelance_stats()["total"])

    def test_legacy_workzilla_setting_is_filtered(self) -> None:
        database.save_freelance_settings(FreelanceSettings(sources=("workzilla", "profi")))
        self.assertEqual(["profi"], database.get_freelance_settings()["sources"])

    def test_archived_orders_are_separate_and_can_be_restored(self) -> None:
        created = database.create_freelance_order(FreelanceOrder(source="fl", external_id="hidden-1", title="Hidden order"))
        self.assertTrue(database.archive_freelance_order(created["id"]))
        self.assertEqual([], database.list_freelance_orders(FreelanceOrderFilters()))
        hidden = database.list_freelance_orders(FreelanceOrderFilters(include_archived=True))
        self.assertEqual(["Hidden order"], [item["title"] for item in hidden])
        self.assertEqual(1, database.freelance_stats()["archived"])
        restored = database.update_freelance_order(created["id"], archived=False)
        self.assertFalse(restored["archived"])
        self.assertEqual(["Hidden order"], [item["title"] for item in database.list_freelance_orders(FreelanceOrderFilters())])


if __name__ == "__main__":
    unittest.main()
