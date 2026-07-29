from __future__ import annotations

from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from backend.main import app


class UsefulLinksDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "useful-links.sqlite3")
        self.path_patch.start()
        database.init_db()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_crud_round_trip_normalizes_url_and_sorts_newest_first(self) -> None:
        first = database.create_useful_link("Figma", "figma.com", "Макеты и прототипы")
        second = database.create_useful_link("MDN", "https://developer.mozilla.org/", "Документация")

        self.assertEqual("https://figma.com", first["url"])
        self.assertEqual(["MDN", "Figma"], [item["title"] for item in database.list_useful_links()["items"]])

        updated = database.update_useful_link(
            int(first["id"]),
            title="Figma Community",
            url="www.figma.com/community/",
            description="Готовые UI-наборы",
        )

        self.assertIsNotNone(updated)
        self.assertEqual("Figma Community", updated["title"])
        self.assertEqual("https://www.figma.com/community", updated["url"])
        self.assertEqual("Готовые UI-наборы", updated["description"])
        self.assertTrue(database.delete_useful_link(int(first["id"])))
        self.assertFalse(database.delete_useful_link(int(first["id"])))
        self.assertEqual([second["id"]], [item["id"] for item in database.list_useful_links()["items"]])

    def test_invalid_and_duplicate_urls_are_rejected(self) -> None:
        for invalid in ("ftp://example.com", "https://", "not a site"):
            with self.subTest(url=invalid):
                with self.assertRaisesRegex(ValueError, "адрес сайта"):
                    database.create_useful_link("Ошибка", invalid, "")

        database.create_useful_link("Figma", "https://figma.com/", "")
        with self.assertRaisesRegex(ValueError, "уже добавлен"):
            database.create_useful_link("Дубликат", "FIGMA.COM", "")

    def test_empty_title_and_excessive_lengths_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "название"):
            database.create_useful_link("   ", "example.com", "")
        with self.assertRaisesRegex(ValueError, "слишком длинное"):
            database.create_useful_link("X" * 121, "example.com", "")
        with self.assertRaisesRegex(ValueError, "слишком длинное"):
            database.create_useful_link("Example", "example.com", "X" * 1001)

    def test_prompts_allow_empty_urls_and_report_category_counts(self) -> None:
        first = database.create_useful_link(
            "Аудит лендинга",
            "",
            "Проанализируй лендинг и найди точки роста.",
            category="prompt",
        )
        second = database.create_useful_link(
            "Сильный оффер",
            "",
            "Сформулируй три варианта оффера.",
            category="prompt",
        )
        website = database.create_useful_link("Figma", "figma.com", "", category="website")

        payload = database.list_useful_links()

        self.assertEqual("", first["url"])
        self.assertEqual("", second["url"])
        self.assertEqual("prompt", first["category"])
        self.assertEqual("website", website["category"])
        self.assertEqual(
            {"prompt": 2, "website": 1, "shop": 0, "article": 0, "other": 0},
            payload["stats"]["categories"],
        )

    def test_prompt_text_and_category_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "текст промпта"):
            database.create_useful_link("Пустой промпт", "", "   ", category="prompt")
        with self.assertRaisesRegex(ValueError, "категор"):
            database.create_useful_link("Неизвестное", "example.com", "", category="video")
        with self.assertRaisesRegex(ValueError, "слишком длин"):
            database.create_useful_link("Огромный промпт", "", "X" * 5001, category="prompt")

    def test_legacy_useful_links_table_is_migrated_without_data_loss(self) -> None:
        with closing(sqlite3.connect(database.DB_PATH)) as connection:
            connection.execute("DROP TABLE useful_links")
            connection.execute(
                """
                CREATE TABLE useful_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO useful_links
                    (id, title, url, description, created_at, updated_at)
                VALUES
                    (7, 'Старый сайт', 'https://example.com', 'Сохранённое описание',
                     '2026-07-28T10:00:00+00:00', '2026-07-28T11:00:00+00:00')
                """
            )
            connection.commit()

        database.init_db()
        migrated = database.list_useful_links()["items"]
        prompt = database.create_useful_link(
            "Новый промпт",
            "",
            "Продолжи текст.",
            category="prompt",
        )

        self.assertEqual(1, len(migrated))
        self.assertEqual(7, migrated[0]["id"])
        self.assertEqual("website", migrated[0]["category"])
        self.assertEqual("https://example.com", migrated[0]["url"])
        self.assertGreater(prompt["id"], 7)


class UsefulLinksApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "useful-links-api.sqlite3")
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

    def test_crud_round_trip(self) -> None:
        created = self.client.post(
            "/api/useful-links",
            json={"title": "Figma", "url": "figma.com", "description": "Макеты"},
        )
        self.assertEqual(201, created.status_code, created.text)
        link_id = created.json()["id"]

        listed = self.client.get("/api/useful-links")
        self.assertEqual(1, listed.json()["stats"]["total"])
        self.assertEqual("https://figma.com", listed.json()["items"][0]["url"])

        updated = self.client.put(
            f"/api/useful-links/{link_id}",
            json={"title": "Figma Community", "description": "UI-наборы"},
        )
        self.assertEqual(200, updated.status_code, updated.text)
        self.assertEqual("Figma Community", updated.json()["title"])
        self.assertEqual("UI-наборы", updated.json()["description"])

        deleted = self.client.delete(f"/api/useful-links/{link_id}")
        self.assertEqual({"ok": True, "deleted_id": link_id}, deleted.json())
        self.assertEqual([], self.client.get("/api/useful-links").json()["items"])

    def test_invalid_url_duplicate_and_missing_rows_return_clear_statuses(self) -> None:
        invalid = self.client.post(
            "/api/useful-links",
            json={"title": "Ошибка", "url": "ftp://example.com", "description": ""},
        )
        self.assertEqual(422, invalid.status_code)
        self.assertIn("адрес сайта", invalid.json()["detail"].lower())

        self.client.post(
            "/api/useful-links",
            json={"title": "Figma", "url": "figma.com", "description": ""},
        )
        duplicate = self.client.post(
            "/api/useful-links",
            json={"title": "Figma снова", "url": "https://FIGMA.COM/", "description": ""},
        )
        self.assertEqual(409, duplicate.status_code)
        self.assertEqual("Этот сайт уже добавлен", duplicate.json()["detail"])

        self.assertEqual(404, self.client.put("/api/useful-links/999", json={"title": "Нет"}).status_code)
        self.assertEqual(404, self.client.delete("/api/useful-links/999").status_code)

    def test_mutations_require_requested_with_header(self) -> None:
        response = self.client.post(
            "/api/useful-links",
            headers={"X-Requested-With": ""},
            json={"title": "Figma", "url": "figma.com", "description": ""},
        )

        self.assertEqual(403, response.status_code)
        self.assertIn("X-Requested-With", response.json()["detail"])

    def test_prompt_crud_and_legacy_default_category(self) -> None:
        prompt = self.client.post(
            "/api/useful-links",
            json={
                "title": "Аудит лендинга",
                "category": "prompt",
                "url": "",
                "description": "Проанализируй первый экран лендинга.",
            },
        )
        legacy = self.client.post(
            "/api/useful-links",
            json={"title": "Figma", "url": "figma.com", "description": "Макеты"},
        )

        self.assertEqual(201, prompt.status_code, prompt.text)
        self.assertEqual("prompt", prompt.json()["category"])
        self.assertEqual("", prompt.json()["url"])
        self.assertEqual(201, legacy.status_code, legacy.text)
        self.assertEqual("website", legacy.json()["category"])

        changed = self.client.put(
            f"/api/useful-links/{legacy.json()['id']}",
            json={
                "category": "prompt",
                "url": "",
                "description": "Сделай прототип интерфейса.",
            },
        )

        self.assertEqual(200, changed.status_code, changed.text)
        self.assertEqual("prompt", changed.json()["category"])
        self.assertEqual("", changed.json()["url"])

    def test_invalid_prompt_payloads_return_422(self) -> None:
        empty_prompt = self.client.post(
            "/api/useful-links",
            json={"title": "Пустой", "category": "prompt", "url": "", "description": ""},
        )
        invalid_category = self.client.post(
            "/api/useful-links",
            json={"title": "Видео", "category": "video", "url": "example.com", "description": ""},
        )

        self.assertEqual(422, empty_prompt.status_code, empty_prompt.text)
        self.assertEqual(422, invalid_category.status_code, invalid_category.text)


if __name__ == "__main__":
    unittest.main()
