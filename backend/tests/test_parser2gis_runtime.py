from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import parser2gis_runtime


class Parser2GisRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def runtime_python(self) -> Path:
        folder = "Scripts" if os.name == "nt" else "bin"
        filename = "python.exe" if os.name == "nt" else "python"
        return self.runtime_dir / folder / filename

    def create_runtime_python(self) -> Path:
        python_path = self.runtime_python()
        python_path.parent.mkdir(parents=True, exist_ok=True)
        python_path.touch()
        return python_path

    def runtime_environment(self) -> dict[str, str]:
        return {
            "PARSER2GIS_RUNTIME_DIR": str(self.runtime_dir),
            "PARSER2GIS_PYTHON": "",
        }

    def test_ready_runtime_returns_upstream_entrypoint_without_installing(self) -> None:
        python_path = self.create_runtime_python()
        probe = subprocess.CompletedProcess([str(python_path)], 0, stdout="")

        with (
            patch.dict(os.environ, self.runtime_environment(), clear=False),
            patch.object(parser2gis_runtime.venv.EnvBuilder, "create") as create_venv,
            patch.object(parser2gis_runtime.subprocess, "run", return_value=probe) as run,
        ):
            command = parser2gis_runtime.ensure_parser2gis_command()

        self.assertEqual(str(python_path), command[0])
        self.assertEqual(["-c", "from parser_2gis import main; main()"], command[1:])
        create_venv.assert_not_called()
        self.assertEqual(1, run.call_count)
        probe_script = run.call_args.args[0][2]
        self.assertIn("version('parser-2gis')", probe_script)
        self.assertIn("1.2.1", probe_script)

    def test_missing_runtime_creates_venv_and_installs_pinned_requirements(self) -> None:
        commands: list[list[str]] = []
        probe_count = 0
        statuses: list[str] = []

        def fake_create(target: str | Path) -> None:
            self.assertEqual(self.runtime_dir, Path(target))
            self.create_runtime_python()

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            nonlocal probe_count
            commands.append(command)
            if command[1] == "-c" and "parser_2gis" in command[2]:
                probe_count += 1
                return subprocess.CompletedProcess(command, 0 if probe_count > 1 else 1, stdout="")
            return subprocess.CompletedProcess(command, 0, stdout="installed")

        with (
            patch.dict(os.environ, self.runtime_environment(), clear=False),
            patch.object(parser2gis_runtime.venv.EnvBuilder, "create", side_effect=fake_create) as create_venv,
            patch.object(parser2gis_runtime.subprocess, "run", side_effect=fake_run),
        ):
            command = parser2gis_runtime.ensure_parser2gis_command(statuses.append)

        create_venv.assert_called_once_with(self.runtime_dir)
        install_command = next(item for item in commands if item[1:4] == ["-m", "pip", "install"])
        self.assertIn("--disable-pip-version-check", install_command)
        self.assertEqual("-r", install_command[-2])
        self.assertEqual(str(parser2gis_runtime.REQUIREMENTS_FILE), install_command[-1])
        self.assertEqual(str(self.runtime_python()), command[0])
        self.assertTrue(any("parser-2gis" in status for status in statuses))

    def test_configured_python_is_used_without_creating_local_runtime(self) -> None:
        custom_python = Path(self.temp_dir.name) / "custom-python.exe"
        custom_python.touch()
        probe = subprocess.CompletedProcess([str(custom_python)], 0, stdout="")
        environment = self.runtime_environment() | {"PARSER2GIS_PYTHON": str(custom_python)}

        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(parser2gis_runtime.venv.EnvBuilder, "create") as create_venv,
            patch.object(parser2gis_runtime.subprocess, "run", return_value=probe),
        ):
            command = parser2gis_runtime.ensure_parser2gis_command()

        self.assertEqual(str(custom_python), command[0])
        create_venv.assert_not_called()

    def test_city_code_is_loaded_from_upstream_city_catalog(self) -> None:
        python_path = self.create_runtime_python()
        result = subprocess.CompletedProcess([str(python_path)], 0, stdout="chelyabinsk\n")

        with patch.object(parser2gis_runtime.subprocess, "run", return_value=result) as run:
            city_code = parser2gis_runtime.resolve_parser2gis_city_code(str(python_path), "Челябинск")

        self.assertEqual("chelyabinsk", city_code)
        self.assertEqual("Челябинск", run.call_args.args[0][-1])


if __name__ == "__main__":
    unittest.main()
