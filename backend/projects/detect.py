from __future__ import annotations

import json
import re
from pathlib import Path

from .models import DetectedProject


# Известные фреймворки: по какой зависимости узнаём и какой порт поднимают по умолчанию.
FRAMEWORK_HINTS: tuple[tuple[str, str, int | None], ...] = (
    ("next", "Next.js", 3000),
    ("nuxt", "Nuxt", 3000),
    ("@remix-run/dev", "Remix", 3000),
    ("astro", "Astro", 4321),
    ("vite", "Vite", 5173),
    ("react-scripts", "Create React App", 3000),
    ("@angular/core", "Angular", 4200),
    ("svelte", "Svelte", 5173),
    ("vue", "Vue", 5173),
    ("react", "React", None),
    ("express", "Express", 3000),
    ("fastify", "Fastify", 3000),
    ("typescript", "TypeScript", None),
    ("tailwindcss", "Tailwind CSS", None),
)

PREFERRED_SCRIPTS = ("dev", "start", "serve", "develop")
PORT_PATTERN = re.compile(r"(?:--port[=\s]+|-p\s+|:)(\d{2,5})")


def _read_json(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _port_from_script(script: str) -> int | None:
    match = PORT_PATTERN.search(script)
    if match is None:
        return None
    port = int(match.group(1))
    return port if 1 <= port <= 65535 else None


def _detect_node(folder: Path, result: DetectedProject) -> DetectedProject:
    manifest = _read_json(folder / "package.json")
    if not manifest:
        return result
    result.kind = "node"
    result.name = str(manifest.get("name") or result.name or folder.name)
    result.description = str(manifest.get("description") or "")
    result.version = str(manifest.get("version") or "")

    scripts = manifest.get("scripts")
    scripts = scripts if isinstance(scripts, dict) else {}
    result.scripts = sorted(str(key) for key in scripts)

    chosen = next((name for name in PREFERRED_SCRIPTS if name in scripts), "")
    if chosen:
        result.command = f"npm run {chosen}"
        result.port = _port_from_script(str(scripts[chosen]))
    elif result.scripts:
        result.command = f"npm run {result.scripts[0]}"

    dependencies: dict[str, object] = {}
    for key in ("dependencies", "devDependencies"):
        value = manifest.get(key)
        if isinstance(value, dict):
            dependencies.update(value)

    for package, label, default_port in FRAMEWORK_HINTS:
        if package in dependencies:
            result.tags.append(label)
            if result.port is None and default_port is not None:
                result.port = default_port
    result.tags = list(dict.fromkeys(result.tags))[:6]
    return result


def _detect_python(folder: Path, result: DetectedProject) -> DetectedProject:
    if (folder / "manage.py").exists():
        result.kind = "django"
        result.command = "python manage.py runserver"
        result.port = result.port or 8000
        result.tags = ["Python", "Django"]
        return result
    requirements = folder / "requirements.txt"
    if not requirements.exists() and not (folder / "pyproject.toml").exists():
        return result
    result.kind = "python"
    result.tags = ["Python"]
    for candidate in ("main.py", "app.py", "run.py", "bot.py"):
        if (folder / candidate).exists():
            result.command = f"python {candidate}"
            break
    dependencies = requirements.read_text(encoding="utf-8", errors="ignore").lower() if requirements.exists() else ""
    if "fastapi" in dependencies and (folder / "main.py").exists():
        result.command = "python -m uvicorn main:app --reload"
        result.port = result.port or 8000
        result.tags.append("FastAPI")
    return result


def detect_project(raw_path: str) -> DetectedProject:
    """Разбирает папку проекта и предлагает название, команду запуска и порт."""

    result = DetectedProject()
    cleaned = (raw_path or "").strip().strip('"').strip("'")
    if not cleaned:
        return result
    folder = Path(cleaned).expanduser()
    if not folder.is_dir():
        return result

    result.exists = True
    result.name = folder.name
    result = _detect_node(folder, result)
    if result.kind == "unknown":
        result = _detect_python(folder, result)
    if result.kind == "unknown" and (folder / "index.html").exists():
        result.kind = "static"
        result.category = "Веб-сайт"
        result.tags = ["HTML"]
    if result.kind in {"python", "django"}:
        result.category = "Скрипт" if result.kind == "python" else "Веб-приложение"
    return result
