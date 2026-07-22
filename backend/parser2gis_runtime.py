from __future__ import annotations

import os
import subprocess
import threading
import venv
from pathlib import Path
from typing import Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = ROOT_DIR / "backend" / "data" / "parser2gis-runtime"
REQUIREMENTS_FILE = Path(__file__).with_name("parser2gis-requirements.txt")
PARSER2GIS_VERSION = "1.2.1"
PARSER_ENTRYPOINT = "from parser_2gis import main; main()"
_RUNTIME_LOCK = threading.Lock()

_VERSION_CHECK_SCRIPT = (
    "from importlib.metadata import version\n"
    "import parser_2gis\n"
    f"raise SystemExit(0 if version('parser-2gis') == '{PARSER2GIS_VERSION}' else 1)"
)

_CITY_LOOKUP_SCRIPT = """
import json
import sys
from pathlib import Path

import parser_2gis

needle = sys.argv[1].strip().casefold()
cities_path = Path(parser_2gis.__file__).resolve().parent / "data" / "cities.json"
cities = json.loads(cities_path.read_text(encoding="utf-8"))
for city in cities:
    if str(city.get("name", "")).strip().casefold() == needle:
        print(city.get("code", ""))
        break
""".strip()


def ensure_parser2gis_command(
    on_status: Callable[[str], None] | None = None,
) -> list[str]:
    """Return an isolated parser-2gis CLI command, installing it when needed."""
    configured = os.getenv("PARSER2GIS_PYTHON", "").strip()
    if configured:
        python_path = _resolve_path(configured)
        if not python_path.is_file():
            raise FileNotFoundError(f"Не найден PARSER2GIS_PYTHON: {python_path}")
        if not _package_is_available(python_path):
            raise RuntimeError(
                f"В PARSER2GIS_PYTHON не установлен parser-2gis=={PARSER2GIS_VERSION}. "
                "Установите нужную версию или удалите эту настройку."
            )
        return [str(python_path), "-c", PARSER_ENTRYPOINT]

    runtime_dir = _runtime_dir()
    python_path = _runtime_python(runtime_dir)
    with _RUNTIME_LOCK:
        if not python_path.is_file():
            if on_status:
                on_status("Подготавливаю отдельное окружение parser-2gis…")
            try:
                venv.EnvBuilder(with_pip=True).create(runtime_dir)
            except Exception as error:  # noqa: BLE001 - expose a concise task error
                raise RuntimeError(f"Не удалось создать окружение parser-2gis: {error}") from error

        if not _package_is_available(python_path):
            if on_status:
                on_status(f"Устанавливаю parser-2gis {PARSER2GIS_VERSION} (только при первом запуске)…")
            _install_package(python_path)
            if not _package_is_available(python_path):
                raise RuntimeError("parser-2gis установился, но не импортируется в отдельном окружении")

    return [str(python_path), "-c", PARSER_ENTRYPOINT]


def resolve_parser2gis_city_code(python_executable: str, city: str) -> str | None:
    """Resolve a display city name through parser-2gis' bundled city catalog."""
    completed = _run(
        [python_executable, "-c", _CITY_LOOKUP_SCRIPT, city],
        timeout=30,
    )
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value.splitlines()[-1].strip() if value else None


def _runtime_dir() -> Path:
    configured = os.getenv("PARSER2GIS_RUNTIME_DIR", "").strip()
    return _resolve_path(configured) if configured else DEFAULT_RUNTIME_DIR


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT_DIR / path


def _runtime_python(runtime_dir: Path) -> Path:
    if os.name == "nt":
        return runtime_dir / "Scripts" / "python.exe"
    return runtime_dir / "bin" / "python"


def _package_is_available(python_path: Path) -> bool:
    completed = _run([str(python_path), "-c", _VERSION_CHECK_SCRIPT], timeout=30)
    return completed.returncode == 0


def _install_package(python_path: Path) -> None:
    if not REQUIREMENTS_FILE.is_file():
        raise FileNotFoundError(f"Не найден список зависимостей 2GIS: {REQUIREMENTS_FILE}")
    command = [
        str(python_path),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(REQUIREMENTS_FILE),
    ]
    completed = _run(command, timeout=300)
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout or "").splitlines()[-12:])
        raise RuntimeError(f"Не удалось установить parser-2gis: {tail}")


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    try:
        return subprocess.run(
            command,
            cwd=str(ROOT_DIR),
            env=environment,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Команда parser-2gis превысила лимит {timeout} секунд") from error
