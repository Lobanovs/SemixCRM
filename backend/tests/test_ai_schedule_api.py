from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from backend.ai.client import AiDisabledError, AiError
from backend.main import app


HEADERS = {"X-Requested-With": "SemixCRM"}

PLAN = {
    "week_start": "2026-08-03",
    "week_end": "2026-08-09",
    "focus": "Запуск лендинга",
    "summary": "Сначала собрать материалы, затем проверить результат.",
    "tasks": [
        {
            "id": "ai-1",
            "date": "2026-08-04",
            "time": "10:00",
            "title": "Собрать материалы для лендинга",
            "kind": "task",
            "reason": "Чтобы не отвлекаться во время сборки.",
        }
    ],
}


class AiScheduleApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "ai-schedule-api.sqlite3"
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

    def test_generation_requires_guard_and_receives_current_schedule(self) -> None:
        database.create_schedule_task("2026-08-03", "Проверить текущую форму", "09:00")
        database.save_schedule_week(
            "2026-08-03",
            "Текущая неделя",
            [{"title": "Запустить лендинг", "done": False}],
        )
        request = {
            "week_start": "2026-08-03",
            "objective": "Подготовить запуск",
            "intensity": "balanced",
            "include_weekend": False,
        }

        forbidden = self.client.post("/api/ai/schedule/plan", json=request)
        self.assertEqual(403, forbidden.status_code)

        with patch("backend.main.generate_week_plan", return_value=PLAN) as generator:
            response = self.client.post("/api/ai/schedule/plan", headers=HEADERS, json=request)

        self.assertEqual(200, response.status_code)
        self.assertEqual(PLAN, response.json())
        arguments = generator.call_args.kwargs
        self.assertEqual("Подготовить запуск", arguments["objective"])
        self.assertEqual("Проверить текущую форму", arguments["schedule"]["tasks"][0]["title"])
        self.assertEqual("Запустить лендинг", arguments["schedule"]["goals"][0]["title"])

    def test_generation_maps_disabled_and_provider_errors(self) -> None:
        request = {
            "week_start": "2026-08-03",
            "objective": "Подготовить запуск",
            "intensity": "balanced",
            "include_weekend": False,
        }
        with patch("backend.main.generate_week_plan", side_effect=AiDisabledError("нет ключа")):
            disabled = self.client.post("/api/ai/schedule/plan", headers=HEADERS, json=request)
        with patch("backend.main.generate_week_plan", side_effect=AiError("провайдер недоступен")):
            provider = self.client.post("/api/ai/schedule/plan", headers=HEADERS, json=request)

        self.assertEqual(503, disabled.status_code)
        self.assertIn("Настройках", disabled.json()["detail"])
        self.assertEqual(502, provider.status_code)
        self.assertEqual("провайдер недоступен", provider.json()["detail"])

    def test_apply_skips_duplicates_preserves_week_data_and_returns_schedule(self) -> None:
        database.create_schedule_task("2026-08-04", "Собрать материалы", "09:00")
        database.save_schedule_week(
            "2026-08-03",
            "Существующее описание",
            [{"title": "Старая цель", "done": False}],
            "Старый фокус",
        )
        response = self.client.post(
            "/api/ai/schedule/plan/apply",
            headers=HEADERS,
            json={
                "week_start": "2026-08-03",
                "focus": "Новый AI-фокус",
                "tasks": [
                    {
                        "date": "2026-08-04",
                        "time": "14:00",
                        "title": "собрать МАТЕРИАЛЫ",
                        "kind": "task",
                        "reason": "Дубль с другим регистром.",
                    },
                    {
                        "date": "2026-08-05",
                        "time": "11:30",
                        "title": "Проверить финальную версию",
                        "kind": "task",
                        "reason": "Чтобы завершить задачу.",
                    },
                ],
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(1, payload["created_count"])
        self.assertEqual(1, payload["skipped_count"])
        self.assertEqual("Новый AI-фокус", payload["schedule"]["focus"])
        self.assertEqual("Существующее описание", payload["schedule"]["summary"])
        self.assertEqual("Старая цель", payload["schedule"]["goals"][0]["title"])
        self.assertEqual(2, len(payload["schedule"]["tasks"]))

    def test_invalid_batch_is_atomic(self) -> None:
        with self.assertRaisesRegex(ValueError, "выбранной недели"):
            database.apply_schedule_task_batch(
                "2026-08-03",
                [
                    {"date": "2026-08-04", "title": "Валидная задача", "time": "10:00", "kind": "task"},
                    {"date": "2026-08-12", "title": "Чужая неделя", "time": "", "kind": "task"},
                ],
                "Фокус",
            )

        payload = database.get_schedule("2026-08-03")
        self.assertEqual([], payload["tasks"])
        self.assertEqual("", payload["focus"])


if __name__ == "__main__":
    unittest.main()
