from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import backups, database, main


class DatabaseBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database_path = self.root / "semixcrm.sqlite3"
        self.backup_dir = self.root / "backups"
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            connection.execute("INSERT INTO clients (name) VALUES ('Тестовый клиент')")
            connection.commit()
        finally:
            connection.close()
        self.database_patch = patch.object(database, "DB_PATH", self.database_path)
        self.directory_patch = patch.object(backups, "BACKUP_DIR", self.backup_dir)
        self.database_patch.start()
        self.directory_patch.start()

    def tearDown(self) -> None:
        self.directory_patch.stop()
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_creates_a_consistent_sqlite_backup_and_metadata(self) -> None:
        now = datetime(2026, 8, 24, 10, 11, 12, tzinfo=timezone.utc)

        item = backups.create_database_backup(now=now)

        path = self.backup_dir / item["name"]
        self.assertEqual("semixcrm-20260824-101112.sqlite3", item["name"])
        self.assertTrue(path.is_file())
        self.assertGreater(item["size"], 0)
        connection = sqlite3.connect(path)
        try:
            self.assertEqual("ok", connection.execute("PRAGMA integrity_check").fetchone()[0])
            self.assertEqual("Тестовый клиент", connection.execute("SELECT name FROM clients").fetchone()[0])
        finally:
            connection.close()

    def test_same_second_creates_unique_files_and_lists_newest_first(self) -> None:
        now = datetime(2026, 8, 24, 10, 11, 12, tzinfo=timezone.utc)

        first = backups.create_database_backup(now=now)
        second = backups.create_database_backup(now=now)
        listed = backups.list_database_backups()

        self.assertNotEqual(first["name"], second["name"])
        self.assertEqual({first["name"], second["name"]}, {item["name"] for item in listed})

    def test_resolver_rejects_paths_and_unknown_files(self) -> None:
        with self.assertRaises(ValueError):
            backups.resolve_database_backup("../semixcrm.sqlite3")
        with self.assertRaises(FileNotFoundError):
            backups.resolve_database_backup("semixcrm-20260824-101112.sqlite3")


class DatabaseBackupApiTests(unittest.TestCase):
    def test_list_and_create_routes(self) -> None:
        item = {
            "name": "semixcrm-20260824-101112.sqlite3",
            "size": 4096,
            "created_at": "2026-08-24T10:11:12+00:00",
        }
        client = TestClient(main.app, headers={"X-Requested-With": "SemixCRM"})
        with (
            patch.object(main, "list_database_backups", return_value=[item]),
            patch.object(main, "create_database_backup", return_value=item),
        ):
            listed = client.get("/api/backups")
            created = client.post("/api/backups")

        self.assertEqual({"backups": [item]}, listed.json())
        self.assertEqual(201, created.status_code)
        self.assertEqual(item, created.json())

    def test_create_route_requires_the_crm_header(self) -> None:
        response = TestClient(main.app).post("/api/backups")

        self.assertEqual(403, response.status_code)

    def test_download_returns_the_selected_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "semixcrm-20260824-101112.sqlite3"
            path.write_bytes(b"sqlite-backup")
            with patch.object(main, "resolve_database_backup", return_value=path):
                response = TestClient(main.app).get(f"/api/backups/{path.name}")

        self.assertEqual(200, response.status_code)
        self.assertEqual(b"sqlite-backup", response.content)
        self.assertIn("attachment", response.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
