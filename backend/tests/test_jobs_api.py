from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from backend.jobs import storage as jobs_storage
from backend.jobs.models import JobVacancy
from backend.main import app


class JobsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "jobs.sqlite3")
        self.path_patch.start()
        self.registry_patch = patch("backend.main.build_adapters", return_value={})
        self.registry_patch.start()
        self.client_context = TestClient(app, headers={"X-Requested-With": "SemixCRM"})
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.registry_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_list_is_empty_before_any_vacancy(self) -> None:
        response = self.client.get("/api/jobs")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual([], payload["jobs"])
        self.assertEqual(0, payload["stats"]["total"])
        self.assertEqual(["hh", "habr", "telegram", "remoteok", "remotive", "weworkremotely"], payload["available"])

    def test_create_update_and_archive_round_trip(self) -> None:
        created = self.client.post("/api/jobs", json={"role": "Frontend-разработчик", "company": "Яндекс"})
        self.assertEqual(201, created.status_code)
        job_id = created.json()["id"]

        updated = self.client.put(f"/api/jobs/{job_id}", json={"status": "Откликнулся"})
        self.assertEqual(200, updated.status_code)
        self.assertEqual("Откликнулся", updated.json()["status"])
        # Следующий шаг выводится из статуса, пока пользователь не задал свой.
        self.assertEqual("Жду ответа", updated.json()["next_step"])

        archived = self.client.put(f"/api/jobs/{job_id}", json={"archived": True})
        self.assertTrue(archived.json()["archived"])
        self.assertEqual([], self.client.get("/api/jobs").json()["jobs"])
        self.assertEqual(1, len(self.client.get("/api/jobs?archived=true").json()["jobs"]))

    def test_archive_all_moves_every_active_job_and_is_idempotent(self) -> None:
        first_id = self.client.post("/api/jobs", json={"role": "Frontend"}).json()["id"]
        old_id = self.client.post("/api/jobs", json={"role": "Уже в архиве"}).json()["id"]
        self.client.post("/api/jobs", json={"role": "Backend"})
        self.client.put(f"/api/jobs/{old_id}", json={"archived": True})

        response = self.client.post("/api/jobs/archive-all")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True, "archived_count": 2}, response.json())
        self.assertEqual([], self.client.get("/api/jobs").json()["jobs"])
        archived = self.client.get("/api/jobs?archived=true").json()["jobs"]
        self.assertEqual(3, len(archived))
        self.assertIn(first_id, [item["id"] for item in archived])
        self.assertEqual(0, self.client.post("/api/jobs/archive-all").json()["archived_count"])

    def test_custom_next_step_is_not_overwritten_by_status(self) -> None:
        job_id = self.client.post("/api/jobs", json={"role": "Backend"}).json()["id"]

        updated = self.client.put(f"/api/jobs/{job_id}", json={"status": "Ответили", "next_step": "Позвонить в 15:00"})

        self.assertEqual("Позвонить в 15:00", updated.json()["next_step"])

    def test_unknown_status_is_rejected(self) -> None:
        job_id = self.client.post("/api/jobs", json={"role": "QA"}).json()["id"]

        response = self.client.put(f"/api/jobs/{job_id}", json={"status": "Придумал"})

        self.assertEqual(422, response.status_code)

    def test_two_manual_vacancies_with_the_same_title_stay_separate(self) -> None:
        first = self.client.post("/api/jobs", json={"role": "Разработчик", "company": "A"})
        second = self.client.post("/api/jobs", json={"role": "Разработчик", "company": "B"})

        self.assertNotEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(2, self.client.get("/api/jobs").json()["stats"]["total"])

    def test_missing_vacancy_returns_404(self) -> None:
        self.assertEqual(404, self.client.put("/api/jobs/999", json={"status": "Оффер"}).status_code)
        self.assertEqual(404, self.client.delete("/api/jobs/999").status_code)

    def test_settings_round_trip_and_source_validation(self) -> None:
        payload = {
            "sources": ["hh", "telegram"],
            "keywords": ["react", "typescript"],
            "excluded_keywords": ["стажёр"],
            "telegram_channels": ["@forfrontend"],
            "area": "Казань",
            "salary_min": 150000,
            "remote_only": True,
            "per_source_limit": 40,
        }
        saved = self.client.put("/api/jobs/settings", json=payload)

        self.assertEqual(200, saved.status_code)
        # Собачка перед каналом убирается на сохранении.
        self.assertEqual(["forfrontend"], saved.json()["telegram_channels"])
        self.assertEqual("Казань", self.client.get("/api/jobs/settings").json()["area"])

        rejected = self.client.put("/api/jobs/settings", json={**payload, "sources": ["superjob"]})
        self.assertEqual(422, rejected.status_code)

    def test_search_and_status_filters_narrow_the_list(self) -> None:
        self.client.post("/api/jobs", json={"role": "React разработчик", "company": "Яндекс"})
        backend_id = self.client.post("/api/jobs", json={"role": "Go разработчик", "company": "Сбер"}).json()["id"]
        self.client.put(f"/api/jobs/{backend_id}", json={"status": "Отказ"})

        self.assertEqual(1, len(self.client.get("/api/jobs?query=react").json()["jobs"]))
        self.assertEqual(1, len(self.client.get("/api/jobs?status=Отказ").json()["jobs"]))
        self.assertEqual(0, len(self.client.get("/api/jobs?query=python").json()["jobs"]))

    def test_stats_track_pipeline_stages(self) -> None:
        applied = self.client.post("/api/jobs", json={"role": "A"}).json()["id"]
        interview = self.client.post("/api/jobs", json={"role": "B"}).json()["id"]
        self.client.put(f"/api/jobs/{applied}", json={"status": "Откликнулся"})
        self.client.put(f"/api/jobs/{interview}", json={"status": "Собеседование"})

        stats = self.client.get("/api/jobs").json()["stats"]

        self.assertEqual(2, stats["total"])
        self.assertEqual(1, stats["applied"])
        self.assertEqual(1, stats["interviews"])
        self.assertEqual(50, stats["conversion"])

    def test_parse_run_history_is_recorded(self) -> None:
        jobs_storage.record_job_run("run-1", "2026-07-26T10:00:00+00:00", "done", 3, 1, ["hh"], "Готово")

        runs = self.client.get("/api/jobs/runs").json()["runs"]

        self.assertEqual(1, len(runs))
        self.assertEqual(3, runs[0]["inserted_count"])
        self.assertEqual(["hh"], runs[0]["sources"])

    def test_unknown_parse_run_reports_missing(self) -> None:
        response = self.client.get("/api/jobs/parse/нет-такого")

        self.assertEqual(200, response.status_code)
        self.assertEqual("missing", response.json()["status"])


class JobsStorageDedupeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "jobs.sqlite3")
        self.path_patch.start()
        database.init_db()
        jobs_storage.init_jobs_schema()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_same_external_id_updates_instead_of_duplicating(self) -> None:
        vacancy = JobVacancy(source="hh", external_id="hh-1", company="Яндекс", role="Frontend", discovered_at="2026-07-26T10:00:00+00:00")
        first, created = jobs_storage.create_job(vacancy, 10, ["в названии"], 50)
        second, created_again = jobs_storage.create_job(
            JobVacancy(**{**vacancy.__dict__, "salary_min": 200000, "salary_text": "от 200 000 ₽"}), 12, ["зарплата"], 60,
        )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(200000, second["salary_min"])

    def test_user_status_survives_a_repeated_find(self) -> None:
        vacancy = JobVacancy(source="hh", external_id="hh-2", company="VK", role="Node.js", discovered_at="2026-07-26T10:00:00+00:00")
        stored, _ = jobs_storage.create_job(vacancy)
        jobs_storage.update_job(stored["id"], status="Собеседование", note="Созвон в четверг")

        jobs_storage.create_job(vacancy)
        refreshed = jobs_storage.get_job(stored["id"])

        self.assertEqual("Собеседование", refreshed["status"])
        self.assertEqual("Созвон в четверг", refreshed["note"])

    def test_vacancy_without_role_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            jobs_storage.create_job(JobVacancy(source="hh", external_id="hh-3", company="X", role="  "))


if __name__ == "__main__":
    unittest.main()
