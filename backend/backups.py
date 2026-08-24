from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import database


BACKUP_DIR = Path(
    os.getenv("SEMIXCRM_BACKUP_DIR", str(database.DB_PATH.parent / "backups"))
)
BACKUP_NAME = re.compile(r"^semixcrm-\d{8}-\d{6}(?:-\d{2})?\.sqlite3$")


def _metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def _next_path(now: datetime) -> Path:
    base = f"semixcrm-{now.astimezone(timezone.utc):%Y%m%d-%H%M%S}"
    candidate = BACKUP_DIR / f"{base}.sqlite3"
    suffix = 1
    while candidate.exists():
        candidate = BACKUP_DIR / f"{base}-{suffix:02d}.sqlite3"
        suffix += 1
    return candidate


def create_database_backup(*, now: datetime | None = None) -> dict[str, Any]:
    """Create a transactionally consistent SQLite snapshot using the backup API."""

    source_path = database.DB_PATH
    if not source_path.is_file():
        raise FileNotFoundError("База Semix CRM ещё не создана")

    created_at = now or datetime.now(timezone.utc)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target_path = _next_path(created_at)
    try:
        with closing(sqlite3.connect(source_path, timeout=30)) as source, closing(sqlite3.connect(target_path)) as target:
            with target:
                source.backup(target)
        with closing(sqlite3.connect(target_path)) as check:
            integrity = check.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise sqlite3.DatabaseError("Проверка целостности резервной копии не пройдена")
        os.utime(target_path, (created_at.timestamp(), created_at.timestamp()))
        return _metadata(target_path)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise


def list_database_backups() -> list[dict[str, Any]]:
    if not BACKUP_DIR.is_dir():
        return []
    items = [
        _metadata(path)
        for path in BACKUP_DIR.iterdir()
        if path.is_file() and BACKUP_NAME.fullmatch(path.name)
    ]
    return sorted(items, key=lambda item: (item["created_at"], item["name"]), reverse=True)


def resolve_database_backup(filename: str) -> Path:
    if not BACKUP_NAME.fullmatch(filename):
        raise ValueError("Некорректное имя резервной копии")
    path = BACKUP_DIR / filename
    if not path.is_file():
        raise FileNotFoundError("Резервная копия не найдена")
    return path
