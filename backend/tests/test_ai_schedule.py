from __future__ import annotations

import unittest
from datetime import date
from typing import Any, Callable

from backend.ai.client import AiError
from backend.ai.schedule import generate_week_plan


SCHEDULE = {
    "tasks": [
        {
            "id": 1,
            "date": "2026-08-03",
            "time": "10:00",
            "title": "Проверить форму заявки",
            "kind": "task",
            "done": False,
        }
    ],
    "goals": [
        {"title": "Запустить лендинг", "done": False},
        {"title": "Закрытая цель", "done": True},
    ],
    "summary": "Фокус на запуске",
}

VALID_PAYLOAD = {
    "focus": "Запуск лендинга без аврала",
    "summary": "Сначала завершить структуру, затем проверить и опубликовать.",
    "tasks": [
        {
            "date": "2026-08-04",
            "time": "11:00",
            "title": "Собрать список оставшихся блоков",
            "kind": "task",
            "reason": "Чтобы видеть точный объём работы.",
        },
        {
            "date": "2026-08-05",
            "time": "",
            "title": "Проверить адаптивность страниц",
            "kind": "task",
            "reason": "Чтобы не выпускать заметные ошибки.",
        },
    ],
}


class FakeAiClient:
    enabled = True

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.system = ""
        self.user = ""

    def complete_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        max_tokens: int = 1600,
        *,
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        self.system = system
        self.user = user
        if validate is not None:
            validate(self.payload)
        return self.payload


class AiSchedulePlanningTests(unittest.TestCase):
    def generate(self, payload: dict[str, Any], **overrides: Any) -> tuple[dict[str, Any], FakeAiClient]:
        client = FakeAiClient(payload)
        arguments = {
            "week_start": "2026-08-03",
            "objective": "Закончить лендинг",
            "intensity": "balanced",
            "include_weekend": False,
            "schedule": SCHEDULE,
            "ai_client": client,
            "today": date(2026, 8, 3),
        }
        arguments.update(overrides)
        return generate_week_plan(**arguments), client

    def test_normalizes_plan_and_includes_schedule_context_in_prompt(self) -> None:
        result, client = self.generate(VALID_PAYLOAD)

        self.assertEqual("2026-08-03", result["week_start"])
        self.assertEqual("2026-08-09", result["week_end"])
        self.assertEqual("ai-1", result["tasks"][0]["id"])
        self.assertEqual("Собрать список оставшихся блоков", result["tasks"][0]["title"])
        self.assertIn("Запустить лендинг", client.user)
        self.assertNotIn("Закрытая цель", client.user)
        self.assertIn("Проверить форму заявки", client.user)
        self.assertIn("Закончить лендинг", client.user)

    def test_removes_same_plan_and_existing_schedule_duplicates(self) -> None:
        payload = {
            **VALID_PAYLOAD,
            "tasks": [
                VALID_PAYLOAD["tasks"][0],
                {**VALID_PAYLOAD["tasks"][0], "time": "14:00"},
                {
                    "date": "2026-08-03",
                    "time": "10:00",
                    "title": "Проверить форму заявки",
                    "kind": "task",
                    "reason": "Уже существует.",
                },
            ],
        }

        result, _ = self.generate(payload)

        self.assertEqual(1, len(result["tasks"]))
        self.assertEqual("Собрать список оставшихся блоков", result["tasks"][0]["title"])

    def test_rejects_task_outside_selected_week(self) -> None:
        payload = {**VALID_PAYLOAD, "tasks": [{**VALID_PAYLOAD["tasks"][0], "date": "2026-08-10"}]}
        with self.assertRaisesRegex(AiError, "выбранной недели"):
            self.generate(payload)

    def test_rejects_past_day_in_current_week(self) -> None:
        payload = {**VALID_PAYLOAD, "tasks": [{**VALID_PAYLOAD["tasks"][0], "date": "2026-08-03"}]}
        with self.assertRaisesRegex(AiError, "прошедший день"):
            self.generate(payload, today=date(2026, 8, 5))

    def test_rejects_weekend_when_disabled(self) -> None:
        payload = {**VALID_PAYLOAD, "tasks": [{**VALID_PAYLOAD["tasks"][0], "date": "2026-08-08"}]}
        with self.assertRaisesRegex(AiError, "выходн"):
            self.generate(payload)

    def test_allows_weekend_when_enabled(self) -> None:
        payload = {**VALID_PAYLOAD, "tasks": [{**VALID_PAYLOAD["tasks"][0], "date": "2026-08-08"}]}
        result, _ = self.generate(payload, include_weekend=True)
        self.assertEqual("2026-08-08", result["tasks"][0]["date"])

    def test_rejects_invalid_time(self) -> None:
        payload = {**VALID_PAYLOAD, "tasks": [{**VALID_PAYLOAD["tasks"][0], "time": "25:90"}]}
        with self.assertRaisesRegex(AiError, "время"):
            self.generate(payload)

    def test_rejects_unsupported_kind(self) -> None:
        payload = {**VALID_PAYLOAD, "tasks": [{**VALID_PAYLOAD["tasks"][0], "kind": "event"}]}
        with self.assertRaisesRegex(AiError, "тип задачи"):
            self.generate(payload)

    def test_rejects_empty_and_oversized_plans(self) -> None:
        with self.assertRaisesRegex(AiError, "хотя бы одну"):
            self.generate({**VALID_PAYLOAD, "tasks": []})
        oversized = {
            **VALID_PAYLOAD,
            "tasks": [
                {**VALID_PAYLOAD["tasks"][0], "title": f"Задача {index}"}
                for index in range(21)
            ],
        }
        with self.assertRaisesRegex(AiError, "не более 20"):
            self.generate(oversized)


if __name__ == "__main__":
    unittest.main()
