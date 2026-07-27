from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from backend.projects import storage
from backend.projects.detect import detect_project
from backend.projects.models import Project
from backend.projects.runner import ProjectRunner


class ProjectStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "projects.sqlite3")
        self.path_patch.start()
        database.init_db()
        storage.init_projects_schema()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_create_and_list_round_trip(self) -> None:
        created = storage.create_project(Project(
            name="Личный сайт", description="Портфолио", path=r"C:\sites\portfolio",
            command="npm run dev", port=5173, category="Веб-сайт", progress=40,
        ), tags=["Next.js", "TypeScript"])

        self.assertEqual("Личный сайт", created["name"])
        self.assertEqual(5173, created["port"])
        self.assertEqual(["Next.js", "TypeScript"], created["tags"])
        self.assertEqual([created["id"]], [item["id"] for item in storage.list_projects()])

    def test_same_folder_cannot_be_added_twice(self) -> None:
        storage.create_project(Project(name="Первый", path=r"C:\sites\one"))

        with self.assertRaises(ValueError):
            storage.create_project(Project(name="Второй", path=r"C:\sites\one"))

    def test_projects_without_path_do_not_collide(self) -> None:
        storage.create_project(Project(name="Идея А"))
        storage.create_project(Project(name="Идея Б"))

        self.assertEqual(2, len(storage.list_projects()))

    def test_update_rejects_unknown_status(self) -> None:
        project = storage.create_project(Project(name="Проект"))

        with self.assertRaises(ValueError):
            storage.update_project(project["id"], status="Неизвестно")

    def test_archived_projects_are_hidden_but_readable(self) -> None:
        project = storage.create_project(Project(name="Старый"))
        storage.update_project(project["id"], archived=True)

        self.assertEqual([], storage.list_projects())
        self.assertEqual(1, len(storage.list_projects(include_archived=True)))

    def test_stats_count_statuses_and_starts(self) -> None:
        storage.create_project(Project(name="A", status="В работе"))
        storage.create_project(Project(name="B", status="Готов"))
        paused = storage.create_project(Project(name="C", status="Пауза"))
        storage.mark_project_started(paused["id"])

        stats = storage.project_stats()

        self.assertEqual(3, stats["total"])
        self.assertEqual(2, stats["active"])
        self.assertEqual(1, stats["done"])
        self.assertEqual(1, stats["started_today"])

    def test_update_returns_none_for_missing_project(self) -> None:
        self.assertIsNone(storage.update_project(9999, name="Нет такого"))


class ProjectDetectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_reports_missing_folder(self) -> None:
        detected = detect_project(str(self.folder / "нет-такой-папки"))

        self.assertFalse(detected.exists)
        self.assertEqual("unknown", detected.kind)

    def test_reads_node_manifest_and_picks_dev_script(self) -> None:
        (self.folder / "package.json").write_text(json.dumps({
            "name": "my-shop",
            "description": "Интернет-магазин",
            "version": "1.4.0",
            "scripts": {"build": "vite build", "dev": "vite --port 4300"},
            "dependencies": {"react": "^19.0.0", "vite": "^8.0.0"},
        }), encoding="utf-8")

        detected = detect_project(str(self.folder))

        self.assertTrue(detected.exists)
        self.assertEqual("node", detected.kind)
        self.assertEqual("my-shop", detected.name)
        self.assertEqual("1.4.0", detected.version)
        self.assertEqual("npm run dev", detected.command)
        self.assertEqual(4300, detected.port)
        self.assertIn("React", detected.tags)

    def test_falls_back_to_framework_default_port(self) -> None:
        (self.folder / "package.json").write_text(json.dumps({
            "name": "site", "scripts": {"dev": "next dev"}, "dependencies": {"next": "^15.0.0"},
        }), encoding="utf-8")

        detected = detect_project(str(self.folder))

        self.assertEqual(3000, detected.port)
        self.assertIn("Next.js", detected.tags)

    def test_detects_python_entry_point(self) -> None:
        (self.folder / "requirements.txt").write_text("httpx\n", encoding="utf-8")
        (self.folder / "bot.py").write_text("print('hi')\n", encoding="utf-8")

        detected = detect_project(str(self.folder))

        self.assertEqual("python", detected.kind)
        self.assertEqual("python bot.py", detected.command)
        self.assertEqual(["Python"], detected.tags)

    def test_detects_static_site(self) -> None:
        (self.folder / "index.html").write_text("<html></html>", encoding="utf-8")

        detected = detect_project(str(self.folder))

        self.assertEqual("static", detected.kind)
        self.assertEqual("Веб-сайт", detected.category)


class ProjectRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runner = ProjectRunner()

    def tearDown(self) -> None:
        self.runner.stop_all()
        self.temp_dir.cleanup()

    def _project(self, command: str, path: str | None = None) -> dict[str, object]:
        return {"id": 1, "name": "Тестовый", "command": command, "path": path or self.temp_dir.name, "url": "", "port": None}

    def test_refuses_project_without_command(self) -> None:
        with self.assertRaises(ValueError):
            self.runner.start(self._project(""))

    def test_refuses_missing_folder(self) -> None:
        with self.assertRaises(ValueError):
            self.runner.start(self._project("echo hi", str(Path(self.temp_dir.name) / "нет")))

    def test_runs_command_and_captures_output(self) -> None:
        command = f'"{sys.executable}" -c "print(\'Local: http://localhost:4321/\')"'

        runtime = self.runner.start(self._project(command))
        self.assertEqual(1, runtime["project_id"])

        for _ in range(50):
            if not self.runner.is_running(1) and self.runner.logs(1):
                break
            time.sleep(0.1)

        logs = self.runner.logs(1)
        self.assertTrue(any("localhost:4321" in line for line in logs), logs)
        # Адрес дев-сервера вычитывается из его же вывода.
        self.assertEqual("http://localhost:4321/", self.runner.status(self._project(command))["url"])

    def test_second_start_while_running_is_rejected(self) -> None:
        command = f'"{sys.executable}" -c "import time; time.sleep(20)"'
        self.runner.start(self._project(command))

        with self.assertRaises(ValueError):
            self.runner.start(self._project(command))

    def test_stop_terminates_process_and_reports_stopped(self) -> None:
        command = f'"{sys.executable}" -c "import time; time.sleep(20)"'
        self.runner.start(self._project(command))
        self.assertTrue(self.runner.is_running(1))

        result = self.runner.stop(1)

        self.assertEqual("stopped", result["status"])
        self.assertFalse(self.runner.is_running(1))

    def _script_command(self, body: str) -> str:
        """Кладёт скрипт в файл: кавычки внутри -c ломались бы оболочкой Windows."""

        script = Path(self.temp_dir.name) / "fake_dev_server.py"
        script.write_text(body, encoding="utf-8")
        return f'"{sys.executable}" "{script}"'

    def _wait_for_exit(self) -> None:
        for _ in range(80):
            if not self.runner.is_running(1):
                return
            time.sleep(0.1)

    def test_ansi_colours_are_stripped_from_logs_and_url(self) -> None:
        # Vite печатает адрес в цвете: без очистки он попадал в ссылку целиком.
        command = self._script_command(
            "import sys\n"
            "sys.stdout.reconfigure(encoding='utf-8')\n"
            r"print('  \x1b[32m>\x1b[39m  \x1b[1mLocal\x1b[22m:   "
            r"\x1b[36mhttp://127.0.0.1:\x1b[1m5205\x1b[22m/\x1b[39m')"
            "\n"
        )

        self.runner.start(self._project(command))
        self._wait_for_exit()

        logs = self.runner.logs(1)
        self.assertTrue(logs)
        self.assertNotIn("\x1b", "".join(logs))
        self.assertIn(">  Local:   http://127.0.0.1:5205/", logs[0])

        status = self.runner.status(self._project(command))
        self.assertEqual("http://127.0.0.1:5205/", status["url"])
        self.assertEqual(5205, status["port"])

    def test_busy_port_failure_is_explained_in_words(self) -> None:
        command = self._script_command(
            "import sys\nprint('Error: Port 5203 is already in use')\nsys.exit(1)\n"
        )

        self.runner.start(self._project(command))
        self._wait_for_exit()

        status = self.runner.status(self._project(command))
        self.assertEqual("failed", status["status"])
        self.assertIn("Порт 5203 уже занят", status["reason"])

    def test_missing_dependencies_failure_is_explained(self) -> None:
        command = self._script_command(
            "import sys\nprint('Error: Cannot find module vite')\nsys.exit(1)\n"
        )

        self.runner.start(self._project(command))
        self._wait_for_exit()

        self.assertIn("npm install", self.runner.status(self._project(command))["reason"])

    def test_status_of_unknown_project_is_stopped(self) -> None:
        status = self.runner.status({"id": 42, "url": "http://localhost:3000", "port": 3000})

        self.assertEqual("stopped", status["status"])
        self.assertEqual("http://localhost:3000", status["url"])

    def test_failed_process_is_reported_as_failed(self) -> None:
        command = f'"{sys.executable}" -c "import sys; sys.exit(3)"'
        self.runner.start(self._project(command))

        for _ in range(50):
            if not self.runner.is_running(1):
                break
            time.sleep(0.1)

        status = self.runner.status(self._project(command))
        self.assertEqual("failed", status["status"])
        self.assertEqual(3, status["exit_code"])


class ProjectsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "api.sqlite3")
        self.path_patch.start()
        self.registry_patch = patch("backend.main.build_adapters", return_value={})
        self.registry_patch.start()
        from backend.main import app

        self.client_context = TestClient(app, headers={"X-Requested-With": "SemixCRM"})
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        from backend.main import project_runner

        project_runner.stop_all()
        self.client_context.__exit__(None, None, None)
        self.registry_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def _create(self, name: str, command: str = "", path: str | None = None) -> dict[str, object]:
        response = self.client.post("/api/projects", json={
            "name": name, "command": command, "path": path if path is not None else "",
        })
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    def test_start_all_reports_started_skipped_and_failed(self) -> None:
        runnable = self._create("Живой", f'"{sys.executable}" -c "import time; time.sleep(20)"', self.temp_dir.name)
        self._create("Без команды")
        broken = self._create("Битый путь", "echo hi", str(Path(self.temp_dir.name) / "нет-такой-папки"))

        result = self.client.post("/api/projects/start-all").json()

        self.assertEqual([runnable["id"]], [item["id"] for item in result["started"]])
        self.assertEqual(["не задана команда запуска"], [item["reason"] for item in result["skipped"]])
        self.assertEqual([broken["id"]], [item["id"] for item in result["failed"]])

    def test_start_all_skips_already_running_projects(self) -> None:
        self._create("Живой", f'"{sys.executable}" -c "import time; time.sleep(20)"', self.temp_dir.name)
        self.client.post("/api/projects/start-all")

        second = self.client.post("/api/projects/start-all").json()

        self.assertEqual([], second["started"])
        self.assertEqual(["уже запущен"], [item["reason"] for item in second["skipped"]])

    def test_stop_all_reports_how_many_were_stopped(self) -> None:
        self._create("Первый", f'"{sys.executable}" -c "import time; time.sleep(20)"', self.temp_dir.name)
        self.client.post("/api/projects/start-all")

        stopped = self.client.post("/api/projects/stop-all").json()

        self.assertEqual(1, stopped["stopped_count"])
        self.assertEqual("stopped", self.client.get("/api/projects").json()["runtime"]["1"]["status"])

    def test_bulk_routes_require_the_custom_header(self) -> None:
        from backend.main import app

        with TestClient(app) as bare_client:
            self.assertEqual(403, bare_client.post("/api/projects/start-all").status_code)
            self.assertEqual(403, bare_client.post("/api/projects/stop-all").status_code)

    def test_detect_route_is_not_shadowed_by_the_id_route(self) -> None:
        response = self.client.post("/api/projects/detect", json={"path": self.temp_dir.name})

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["exists"])

    def test_deleting_a_project_stops_its_process(self) -> None:
        project = self._create("Живой", f'"{sys.executable}" -c "import time; time.sleep(20)"', self.temp_dir.name)
        self.client.post(f"/api/projects/{project['id']}/start")

        self.assertEqual(200, self.client.delete(f"/api/projects/{project['id']}").status_code)

        from backend.main import project_runner

        self.assertFalse(project_runner.is_running(project["id"]))


if __name__ == "__main__":
    unittest.main()
