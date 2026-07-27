from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from ..database import _connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def input_hash(payload: dict[str, Any]) -> str:
    """Отпечаток входа. Изменился клиент или профиль — изменится и хеш, кэш обновится сам."""

    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def init_ai_schema() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                input_hash TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(task, entity_type, entity_id)
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS ai_results_hash_idx ON ai_results(task, input_hash)")


def get_cached(task: str, entity_type: str, entity_id: int, expected_hash: str) -> dict[str, Any] | None:
    """Возвращает сохранённый результат, только если вход не менялся."""

    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM ai_results WHERE task = ? AND entity_type = ? AND entity_id = ?",
            (task, entity_type, int(entity_id)),
        ).fetchone()
    if row is None or row["input_hash"] != expected_hash:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        return None
    return {"cached": True, "model": row["model"], "created_at": row["created_at"], **payload}


def _decode_result(row: Any) -> dict[str, Any] | None:
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "input_hash": row["input_hash"],
        "model": row["model"],
        "created_at": row["created_at"],
        "payload": payload,
    }


def get_latest(task: str, entity_type: str, entity_id: int) -> dict[str, Any] | None:
    """Return the latest saved result even when its input is now stale."""

    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM ai_results WHERE task = ? AND entity_type = ? AND entity_id = ?",
            (task, entity_type, int(entity_id)),
        ).fetchone()
    return _decode_result(row) if row is not None else None


def list_latest(task: str, entity_type: str) -> dict[int, dict[str, Any]]:
    """Return saved results for a task in one query, keyed by entity id."""

    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM ai_results WHERE task = ? AND entity_type = ?",
            (task, entity_type),
        ).fetchall()
    results: dict[int, dict[str, Any]] = {}
    for row in rows:
        decoded = _decode_result(row)
        if decoded is not None:
            results[int(row["entity_id"])] = decoded
    return results


def save_result(task: str, entity_type: str, entity_id: int, value_hash: str, model: str, payload: dict[str, Any]) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO ai_results (task, entity_type, entity_id, input_hash, model, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task, entity_type, entity_id) DO UPDATE SET
                input_hash = excluded.input_hash,
                model = excluded.model,
                payload_json = excluded.payload_json,
                created_at = excluded.created_at
            """,
            (task, entity_type, int(entity_id), value_hash, model, json.dumps(payload, ensure_ascii=False), _now()),
        )


def forget_result(task: str, entity_type: str, entity_id: int) -> bool:
    """Убирает сохранённый результат, чтобы следующая генерация была с нуля."""

    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM ai_results WHERE task = ? AND entity_type = ? AND entity_id = ?",
            (task, entity_type, int(entity_id)),
        )
    return cursor.rowcount > 0
