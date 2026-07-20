from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database
from backend.freelance.models import AdapterResult, FreelanceOrder, FreelanceSettings
from backend.freelance.sniper import FreelanceSniper
from backend.freelance.telegram import TelegramNotifier


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def __call__(self, **payload: str) -> bool:
        self.calls.append(payload)
        return True


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send_order(self, order: dict[str, object]) -> bool:
        self.sent.append(order)
        return True


class NewAdapter:
    source = "fl"

    def collect(self, settings: FreelanceSettings) -> AdapterResult:
        return AdapterResult("fl", "done", (FreelanceOrder(source="fl", external_id="new-1", title="Новый заказ", url="https://fl.ru/projects/new-1"),), "2026-07-20T10:00:00+00:00")


class ErrorAdapter:
    source = "profi"

    def collect(self, settings: FreelanceSettings) -> AdapterResult:
        return AdapterResult("profi", "error", checked_at="2026-07-20T10:00:00+00:00", error="Сессия истекла")


class FreelanceSniperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "freelance.sqlite3"
        self.path_patch = patch.object(database, "DB_PATH", self.db_path)
        self.path_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_notifier_rejects_a_different_chat_id(self) -> None:
        transport = FakeTransport()
        notifier = TelegramNotifier(token="test", allowed_chat_id="800395558", transport=transport)
        self.assertFalse(notifier.send_text("999", "blocked"))
        self.assertEqual([], transport.calls)

    def test_sniper_notifies_only_new_orders_and_keeps_source_error(self) -> None:
        notifier = FakeNotifier()
        sniper = FreelanceSniper(registry={"fl": NewAdapter(), "profi": ErrorAdapter()}, notifier=notifier, settings=FreelanceSettings(sources=("fl", "profi"), telegram_enabled=True))
        first = sniper.check_once()
        second = sniper.check_once()
        self.assertEqual(1, first["inserted"])
        self.assertEqual(0, second["inserted"])
        self.assertEqual("error", first["sources"]["profi"]["status"])
        self.assertEqual(1, len(notifier.sent))

    def test_start_and_stop_are_idempotent(self) -> None:
        sniper = FreelanceSniper(registry={}, notifier=FakeNotifier(), settings=FreelanceSettings(sources=()), interval_seconds=60)
        self.assertEqual("running", sniper.start()["status"])
        self.assertEqual("running", sniper.start()["status"])
        self.assertEqual("stopped", sniper.stop()["status"])

    def test_check_records_run_history_with_orders(self) -> None:
        sniper = FreelanceSniper(registry={"fl": NewAdapter()}, notifier=FakeNotifier(), settings=FreelanceSettings(sources=("fl",)))
        result = sniper.check_once()
        self.assertEqual(1, result["inserted"])
        runs = database.list_freelance_runs()
        self.assertEqual(1, len(runs))
        self.assertEqual(1, runs[0]["inserted_count"])
        detail = database.get_freelance_run(runs[0]["id"])
        self.assertEqual(["Новый заказ"], [item["title"] for item in detail["orders"]])


if __name__ == "__main__":
    unittest.main()
