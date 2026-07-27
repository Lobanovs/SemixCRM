"""Регрессии на найденные дефекты: каждый тест падал бы до исправления."""

from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database, main
from backend.freelance.models import FreelanceOrder, FreelanceOrderFilters, FreelanceSettings
from backend.freelance.sniper import FreelanceSniper, SniperBusyError
from backend.parser import build_2gis_search_url
from backend.projects import storage as projects_storage
from backend.projects.models import Project


def lead(**overrides: object) -> dict[str, object]:
    base = {
        "name": "Стоматология Улыбка", "city": "Казань", "niche": "стоматологии", "source": "2GIS",
        "address": "Баумана 10", "phone": "+7 900 111 22 33", "website": "", "card_url": "",
        "social_url": "", "rating": 4.8, "reviews": 44,
    }
    base.update(overrides)
    return base


class ClientDedupeRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "clients.sqlite3")
        self.path_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_archived_company_comes_back_when_found_again(self) -> None:
        database.insert_clients([lead()])
        database.archive_all_clients()
        self.assertEqual([], database.list_clients())

        result = database.insert_clients([lead()])

        self.assertEqual(1, result["duplicate_count"])
        self.assertEqual(1, result["restored_count"])
        self.assertEqual(1, len(database.list_clients()), "архивная запись должна вернуться в список")

    def test_two_branches_do_not_collapse_when_one_lacks_an_address(self) -> None:
        result = database.insert_clients([
            lead(name="Барбершоп Бород", address="Баумана 10", phone="+7 900 111 22 33"),
            lead(name="Барбершоп Бород", address="", phone="+7 900 444 55 66"),
        ])

        self.assertEqual(2, result["inserted_count"])
        self.assertEqual(2, len(database.list_clients()))

    def test_same_company_without_contacts_still_merges(self) -> None:
        result = database.insert_clients([
            lead(name="Кафе Уют", address="Ленина 1", phone="", website=""),
            lead(name="Кафе Уют", address="", phone="", website=""),
        ])

        self.assertEqual(1, result["inserted_count"])
        self.assertEqual(1, result["duplicate_count"])

    def test_matching_phone_merges_records_with_different_names(self) -> None:
        result = database.insert_clients([
            lead(name="Стоматология Улыбка", phone="+7 900 111 22 33"),
            lead(name="Улыбка на Баумана", address="Другая 5", phone="8 900 111 22 33"),
        ])

        self.assertEqual(1, result["inserted_count"])
        self.assertEqual(1, result["duplicate_count"])

    def test_address_qualified_key_is_not_downgraded_on_merge(self) -> None:
        database.insert_clients([lead(name="Дента", city="Казань", address="Кремлёвская 3")])
        database.insert_clients([lead(name="Дента", city="Казань", address="Кремлёвская 3", website="denta.ru")])

        with database._connect() as connection:
            key = connection.execute("SELECT dedupe_key FROM clients").fetchone()["dedupe_key"]

        self.assertGreaterEqual(key.count(":"), 3, f"ключ не должен вырождаться до имя+город: {key}")

    def test_database_runs_in_wal_mode(self) -> None:
        with database._connect() as connection:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

        self.assertEqual("wal", mode.lower())

    def test_heavy_migration_runs_once(self) -> None:
        database.insert_clients([lead()])

        with patch.object(database, "_migrate_and_deduplicate_clients") as migrate:
            database.init_db()

        migrate.assert_not_called()


class FreelanceOrderKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "freelance.sqlite3")
        self.path_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_two_manual_orders_with_the_same_title_do_not_overwrite_each_other(self) -> None:
        first = database.create_freelance_order(FreelanceOrder(source="manual", external_id="", title="Нужен лендинг", description="Первый"))
        second = database.create_freelance_order(FreelanceOrder(source="manual", external_id="", title="Нужен лендинг", description="Второй"))

        self.assertNotEqual(first["id"], second["id"])
        stored = database.list_freelance_orders(FreelanceOrderFilters())
        self.assertEqual({"Первый", "Второй"}, {item["description"] for item in stored})

    def test_scraped_order_with_external_id_still_deduplicates(self) -> None:
        order = FreelanceOrder(source="kwork", external_id="kwork-42", title="Лендинг", url="https://kwork.ru/projects/42/view")
        first = database.create_freelance_order(order)
        second = database.create_freelance_order(order)

        self.assertEqual(first["id"], second["id"])


class ParserUrlTests(unittest.TestCase):
    def test_city_segment_is_percent_encoded_like_the_niche(self) -> None:
        url = build_2gis_search_url("moscow/search/x?utm=1#frag", "кафе")

        # Ни один служебный символ не должен уводить браузер на другой путь 2gis.ru.
        self.assertNotIn("?utm=1", url)
        self.assertNotIn("#frag", url)
        self.assertTrue(url.startswith("https://2gis.ru/moscow%2Fsearch%2Fx"))

    def test_plain_city_code_stays_readable(self) -> None:
        self.assertTrue(build_2gis_search_url("kazan", "стоматологии").startswith("https://2gis.ru/kazan/search/"))

    def test_empty_city_code_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_2gis_search_url("/", "кафе")


class SniperResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "sniper.sqlite3")
        self.path_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def _sniper(self) -> FreelanceSniper:
        return FreelanceSniper(registry={}, notifier=None, settings=FreelanceSettings(sources=("fl",), interval_seconds=45))

    def test_constructor_honours_persisted_interval(self) -> None:
        self.assertEqual(45, self._sniper().interval_seconds)

    def test_loop_survives_a_database_failure(self) -> None:
        sniper = self._sniper()
        with patch.object(database, "record_freelance_run", side_effect=sqlite3.OperationalError("database is locked")):
            sniper.start()
            for _ in range(50):
                if sniper.status()["last_error"]:
                    break
                time.sleep(0.05)
            status = sniper.status()
            sniper.stop()

        self.assertTrue(status["thread_alive"], "поток не должен умирать от ошибки записи")
        self.assertIn("database is locked", status["last_error"])

    def test_status_does_not_claim_running_without_a_thread(self) -> None:
        sniper = self._sniper()
        sniper._status = "running"

        self.assertEqual("stopped", sniper.status()["status"])

    def test_restart_clears_the_stop_flag(self) -> None:
        sniper = self._sniper()
        sniper.stop()
        self.assertTrue(sniper._stop_event.is_set())

        sniper.start()
        try:
            self.assertFalse(sniper._stop_event.is_set())
        finally:
            sniper.stop()

    def test_parallel_check_is_refused(self) -> None:
        sniper = self._sniper()
        sniper._check_lock.acquire()
        try:
            with self.assertRaises(SniperBusyError):
                sniper.check_once()
        finally:
            sniper._check_lock.release()

    def test_run_links_only_newly_found_orders(self) -> None:
        seen = FreelanceOrder(source="fl", external_id="fl-1", title="Старый заказ")
        database.create_freelance_order(seen)

        class Adapter:
            def collect(self, _settings: FreelanceSettings) -> object:
                from backend.freelance.models import AdapterResult
                fresh = FreelanceOrder(source="fl", external_id="fl-2", title="Новый заказ")
                return AdapterResult("fl", "done", (seen, fresh), "2026-07-26T10:00:00+00:00")

        sniper = FreelanceSniper(registry={"fl": Adapter()}, notifier=None, settings=FreelanceSettings(sources=("fl",)))
        result = sniper.check_once()

        detail = database.get_freelance_run(result["run_id"])
        self.assertEqual(1, result["inserted"])
        self.assertEqual(1, result["duplicates"])
        self.assertEqual(["Новый заказ"], [item["title"] for item in detail["orders"]])


class RequestGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "guard.sqlite3")
        self.path_patch.start()
        self.registry_patch = patch("backend.main.build_adapters", return_value={})
        self.registry_patch.start()
        self.client_context = TestClient(app=main.app, headers={"X-Requested-With": "SemixCRM"})
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.registry_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_foreign_origin_cannot_trigger_side_effects(self) -> None:
        response = self.client.post("/api/clients/restore-all", headers={"Origin": "https://evil.example"})

        self.assertEqual(403, response.status_code)

    def test_frontend_origin_is_allowed(self) -> None:
        response = self.client.post("/api/clients/restore-all", headers={"Origin": "http://localhost:5173"})

        self.assertEqual(200, response.status_code)

    def test_reads_are_never_blocked(self) -> None:
        response = self.client.get("/api/health", headers={"Origin": "https://evil.example"})

        self.assertEqual(200, response.status_code)

    def test_powerful_routes_require_the_custom_header(self) -> None:
        project = projects_storage.create_project(Project(name="Проект", path=self.temp_dir.name, command="echo hi"))
        with TestClient(main.app) as bare_client:
            response = bare_client.post(f"/api/projects/{project['id']}/start")

        self.assertEqual(403, response.status_code)
        self.assertIn("X-Requested-With", response.json()["detail"])

    def test_sniper_check_requires_the_custom_header(self) -> None:
        with TestClient(main.app) as bare_client:
            self.assertEqual(403, bare_client.post("/api/freelance/sniper/check").status_code)


class ClientCreateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "create.sqlite3")
        self.path_patch.start()
        self.registry_patch = patch("backend.main.build_adapters", return_value={})
        self.registry_patch.start()
        self.client_context = TestClient(app=main.app, headers={"X-Requested-With": "SemixCRM"})
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.registry_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_padded_name_no_longer_returns_500(self) -> None:
        response = self.client.post("/api/clients", json={"name": "  Кафе Уют  ", "city": "Москва"})

        self.assertEqual(200, response.status_code)
        self.assertEqual("Кафе Уют", response.json()["name"])
        self.assertEqual("inserted", response.json()["outcome"])

    def test_duplicate_is_reported_instead_of_pretending_to_be_new(self) -> None:
        self.client.post("/api/clients", json={"name": "Дента", "city": "Казань", "phone": "+7 900 111 22 33"})

        second = self.client.post("/api/clients", json={"name": "Дента", "city": "Казань", "phone": "8 900 111 22 33"})

        self.assertEqual(200, second.status_code)
        self.assertEqual("duplicate", second.json()["outcome"])

    def test_second_parse_is_refused_while_one_is_running(self) -> None:
        running = main.ParserJob(id="busy", city="Казань", niches=["стоматологии"], sources=["2gis"], limit=5)
        running.status = "running"
        with main.jobs_lock:
            main.jobs.clear()
            main.jobs["busy"] = running
        try:
            response = self.client.post("/api/clients/parse", json={
                "city": "Казань", "niches": ["стоматологии"], "sources": ["2gis"], "limit": 5,
            })
        finally:
            with main.jobs_lock:
                main.jobs.clear()

        self.assertEqual("", response.json()["job_id"])
        self.assertIn("уже работает", response.json()["error"])


if __name__ == "__main__":
    unittest.main()
