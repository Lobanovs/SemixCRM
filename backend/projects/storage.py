from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ..database import _connect
from .models import PROJECT_STATUSES, Project


EDITABLE_FIELDS = {
    "name": "name",
    "description": "description",
    "path": "path",
    "command": "command",
    "url": "url",
    "port": "port",
    "category": "category",
    "status": "status",
    "version": "version",
    "repo_url": "repo_url",
    "progress": "progress",
    "archived": "archived",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def init_projects_schema() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '',
                command TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                port INTEGER,
                tags_json TEXT NOT NULL DEFAULT '[]',
                category TEXT NOT NULL DEFAULT 'Веб-приложение',
                status TEXT NOT NULL DEFAULT 'В работе',
                version TEXT NOT NULL DEFAULT '',
                repo_url TEXT NOT NULL DEFAULT '',
                progress INTEGER NOT NULL DEFAULT 0,
                last_started_at TEXT NOT NULL DEFAULT '',
                run_count INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Одну и ту же папку нельзя добавить дважды, но архивные записи не мешают.
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS projects_path_idx ON projects(path) WHERE path != '' AND archived = 0"
        )


def _serialize(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    return {
        "id": int(item["id"]),
        "name": item["name"],
        "description": item["description"] or "",
        "path": item["path"] or "",
        "command": item["command"] or "",
        "url": item["url"] or "",
        "port": int(item["port"]) if item["port"] is not None else None,
        "tags": _json_list(item["tags_json"]),
        "category": item["category"] or "Другое",
        "status": item["status"] or "В работе",
        "version": item["version"] or "",
        "repo_url": item["repo_url"] or "",
        "progress": int(item["progress"] or 0),
        "last_started_at": item["last_started_at"] or "",
        "run_count": int(item["run_count"] or 0),
        "archived": bool(item["archived"]),
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }


def list_projects(include_archived: bool = False) -> list[dict[str, Any]]:
    clause = "" if include_archived else " WHERE archived = 0"
    with _connect() as connection:
        rows = connection.execute(f"SELECT * FROM projects{clause} ORDER BY updated_at DESC, id DESC").fetchall()
    return [_serialize(row) for row in rows]


def get_project(project_id: int) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _serialize(row) if row is not None else None


def create_project(project: Project, tags: list[str] | None = None) -> dict[str, Any]:
    project.validated()
    stamp = _now()
    with _connect() as connection:
        if project.path:
            existing = connection.execute(
                "SELECT * FROM projects WHERE path = ? AND archived = 0", (project.path,)
            ).fetchone()
            if existing is not None:
                raise ValueError("Проект с такой папкой уже добавлен")
        cursor = connection.execute(
            """
            INSERT INTO projects (
                name, description, path, command, url, port, tags_json, category,
                status, version, repo_url, progress, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.name.strip(),
                project.description.strip(),
                project.path.strip(),
                project.command.strip(),
                project.url.strip(),
                project.port,
                json.dumps(list(tags if tags is not None else project.tags), ensure_ascii=False),
                project.category,
                project.status,
                project.version.strip(),
                project.repo_url.strip(),
                max(0, min(int(project.progress), 100)),
                stamp,
                stamp,
            ),
        )
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _serialize(row)


def update_project(project_id: int, tags: list[str] | None = None, **fields: Any) -> dict[str, Any] | None:
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in fields.items():
        if value is None or key not in EDITABLE_FIELDS:
            continue
        if key == "status" and value not in PROJECT_STATUSES:
            raise ValueError("Неизвестный статус проекта")
        if key == "progress":
            value = max(0, min(int(value), 100))
        if key == "port":
            value = int(value)
            if not (1 <= value <= 65535):
                raise ValueError("Порт должен быть в диапазоне 1–65535")
        if key == "archived":
            value = 1 if value else 0
        assignments.append(f"{EDITABLE_FIELDS[key]} = ?")
        values.append(value.strip() if isinstance(value, str) else value)
    if tags is not None:
        assignments.append("tags_json = ?")
        values.append(json.dumps(list(tags), ensure_ascii=False))
    if not assignments:
        return get_project(project_id)
    assignments.append("updated_at = ?")
    values.append(_now())
    values.append(project_id)
    with _connect() as connection:
        if not connection.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone():
            return None
        try:
            connection.execute(f"UPDATE projects SET {', '.join(assignments)} WHERE id = ?", values)
        except sqlite3.IntegrityError as error:
            raise ValueError("Проект с такой папкой уже добавлен") from error
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _serialize(row)


def delete_project(project_id: int) -> bool:
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return cursor.rowcount > 0


def mark_project_started(project_id: int) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE projects SET last_started_at = ?, run_count = run_count + 1, updated_at = ? WHERE id = ?",
            (_now(), _now(), project_id),
        )


def project_stats() -> dict[str, Any]:
    with _connect() as connection:
        rows = connection.execute("SELECT status, last_started_at FROM projects WHERE archived = 0").fetchall()
    today = datetime.now(timezone.utc).date().isoformat()
    stages = {status: 0 for status in PROJECT_STATUSES}
    started_today = 0
    for row in rows:
        if row["status"] in stages:
            stages[row["status"]] += 1
        if (row["last_started_at"] or "").startswith(today):
            started_today += 1
    return {
        "total": len(rows),
        "active": len(rows) - stages["Пауза"],
        "in_progress": stages["В работе"],
        "done": stages["Готов"],
        "paused": stages["Пауза"],
        "started_today": started_today,
        "stages": stages,
    }
