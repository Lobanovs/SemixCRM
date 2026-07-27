from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..database import _connect
from .models import JOB_NEXT_STEPS, JOB_SOURCES, JOB_STATUSES, JobSettings, JobVacancy


DEFAULT_SETTINGS = JobSettings()


@dataclass(frozen=True)
class JobFilters:
    query: str = ""
    source: str = ""
    status: str = ""
    min_salary: int | None = None
    sort: str = "relevance"
    include_archived: bool = False


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


def _job_key(vacancy: JobVacancy) -> str:
    if vacancy.external_id.strip():
        return f"{vacancy.source}:{vacancy.external_id.strip().lower()}"
    if vacancy.url.strip():
        return f"{vacancy.source}:url:{vacancy.url.strip().lower()}"
    # Без внешнего идентификатора и ссылки две разные вакансии не должны слипаться.
    return f"{vacancy.source}:manual:{uuid.uuid4().hex}"


def init_jobs_schema() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL DEFAULT '',
                dedupe_key TEXT NOT NULL UNIQUE,
                company TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                salary_min INTEGER,
                salary_max INTEGER,
                currency TEXT NOT NULL DEFAULT 'RUB',
                salary_text TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                employment TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                discovered_at TEXT NOT NULL,
                relevance INTEGER NOT NULL DEFAULT 0,
                relevance_reasons_json TEXT NOT NULL DEFAULT '[]',
                match_score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Сохранено',
                next_step TEXT NOT NULL DEFAULT 'Изучить и откликнуться',
                note TEXT NOT NULL DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS job_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                sources_json TEXT NOT NULL,
                keywords_json TEXT NOT NULL DEFAULT '[]',
                excluded_keywords_json TEXT NOT NULL DEFAULT '[]',
                telegram_channels_json TEXT NOT NULL DEFAULT '[]',
                area TEXT NOT NULL DEFAULT 'Россия',
                salary_min INTEGER NOT NULL DEFAULT 0,
                remote_only INTEGER NOT NULL DEFAULT 0,
                per_source_limit INTEGER NOT NULL DEFAULT 50,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS job_runs (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                sources_json TEXT NOT NULL DEFAULT '[]',
                message TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS job_source_checks (
                source TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                found_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status)")
        connection.execute("CREATE INDEX IF NOT EXISTS jobs_discovered_idx ON jobs(discovered_at)")


def _serialize(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    return {
        "id": int(item["id"]),
        "source": item["source"],
        "external_id": item["external_id"],
        "company": item["company"] or "",
        "role": item["role"],
        "description": item["description"] or "",
        "url": item["url"] or "",
        "tags": _json_list(item["tags_json"]),
        "salary_min": item["salary_min"],
        "salary_max": item["salary_max"],
        "currency": item["currency"] or "RUB",
        "salary_text": item["salary_text"] or "",
        "location": item["location"] or "",
        "employment": item["employment"] or "",
        "published_at": item["published_at"] or "",
        "discovered_at": item["discovered_at"],
        "relevance": int(item["relevance"] or 0),
        "relevance_reasons": _json_list(item["relevance_reasons_json"]),
        "match_score": int(item["match_score"] or 0),
        "status": item["status"],
        "next_step": item["next_step"] or "",
        "note": item["note"] or "",
        "archived": bool(item["archived"]),
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }


def create_job(
    vacancy: JobVacancy,
    relevance: int = 0,
    reasons: list[str] | None = None,
    match_score: int = 0,
) -> tuple[dict[str, Any], bool]:
    """Сохраняет вакансию. Возвращает запись и признак «добавлена впервые»."""

    vacancy.validated()
    if vacancy.source not in JOB_SOURCES and vacancy.source != "manual":
        raise ValueError("Неизвестный источник вакансии")
    key = _job_key(vacancy)
    stamp = _now()
    payload = (
        vacancy.source, vacancy.external_id, key, vacancy.company, vacancy.role, vacancy.description,
        vacancy.url, json.dumps(list(vacancy.tags), ensure_ascii=False), vacancy.salary_min, vacancy.salary_max,
        vacancy.currency, vacancy.salary_text, vacancy.location, vacancy.employment, vacancy.published_at,
        vacancy.discovered_at or stamp, relevance, json.dumps(list(reasons or []), ensure_ascii=False),
        match_score, stamp, stamp,
    )
    with _connect() as connection:
        existing = connection.execute("SELECT * FROM jobs WHERE dedupe_key = ?", (key,)).fetchone()
        if existing is not None:
            # Повторная находка обновляет только объективные поля: статус и заметку ведёт пользователь.
            connection.execute(
                """
                UPDATE jobs SET description = ?, url = ?, tags_json = ?, salary_min = ?, salary_max = ?,
                    salary_text = ?, location = ?, employment = ?, relevance = ?, relevance_reasons_json = ?,
                    match_score = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    vacancy.description or existing["description"], vacancy.url or existing["url"],
                    json.dumps(list(vacancy.tags), ensure_ascii=False), vacancy.salary_min, vacancy.salary_max,
                    vacancy.salary_text, vacancy.location, vacancy.employment, relevance,
                    json.dumps(list(reasons or []), ensure_ascii=False), match_score, stamp, existing["id"],
                ),
            )
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (existing["id"],)).fetchone()
            return _serialize(row), False
        try:
            cursor = connection.execute(
                """
                INSERT INTO jobs (
                    source, external_id, dedupe_key, company, role, description, url, tags_json,
                    salary_min, salary_max, currency, salary_text, location, employment, published_at,
                    discovered_at, relevance, relevance_reasons_json, match_score, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
        except sqlite3.IntegrityError:
            row = connection.execute("SELECT * FROM jobs WHERE dedupe_key = ?", (key,)).fetchone()
            return _serialize(row), False
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _serialize(row), True


def list_jobs(filters: JobFilters | None = None) -> list[dict[str, Any]]:
    active = filters or JobFilters()
    clauses = ["archived = ?"]
    values: list[Any] = [1 if active.include_archived else 0]
    if active.source:
        clauses.append("source = ?")
        values.append(active.source)
    if active.status:
        clauses.append("status = ?")
        values.append(active.status)
    if active.min_salary:
        # Порог задан в рублях, поэтому валютные вакансии он не отсекает:
        # сравнивать $80k с 150 000 ₽ напрямую было бы обманом.
        clauses.append("(currency NOT IN ('RUB', 'RUR') OR COALESCE(salary_max, salary_min, 0) >= ?)")
        values.append(int(active.min_salary))
    if active.query:
        clauses.append("(LOWER(role) LIKE ? OR LOWER(company) LIKE ? OR LOWER(description) LIKE ?)")
        pattern = f"%{active.query.strip().lower()}%"
        values.extend([pattern, pattern, pattern])
    order = {
        "relevance": "relevance DESC, discovered_at DESC",
        "new": "discovered_at DESC, id DESC",
        "salary": "COALESCE(salary_max, salary_min, 0) DESC, relevance DESC",
        "company": "company COLLATE NOCASE ASC",
    }.get(active.sort, "relevance DESC, discovered_at DESC")
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM jobs WHERE {' AND '.join(clauses)} ORDER BY {order}", values
        ).fetchall()
    return [_serialize(row) for row in rows]


def get_job(job_id: int) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _serialize(row) if row is not None else None


def update_job(
    job_id: int,
    status: str | None = None,
    next_step: str | None = None,
    note: str | None = None,
    archived: bool | None = None,
) -> dict[str, Any] | None:
    assignments: list[str] = []
    values: list[Any] = []
    if status is not None:
        if status not in JOB_STATUSES:
            raise ValueError("Неизвестный статус вакансии")
        assignments.append("status = ?")
        values.append(status)
        if next_step is None:
            # Следующий шаг выводится из статуса, пока пользователь не задал свой.
            assignments.append("next_step = ?")
            values.append(JOB_NEXT_STEPS.get(status, ""))
    if next_step is not None:
        assignments.append("next_step = ?")
        values.append(next_step.strip())
    if note is not None:
        assignments.append("note = ?")
        values.append(note.strip())
    if archived is not None:
        assignments.append("archived = ?")
        values.append(1 if archived else 0)
    if not assignments:
        return get_job(job_id)
    assignments.append("updated_at = ?")
    values.extend([_now(), job_id])
    with _connect() as connection:
        if not connection.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone():
            return None
        connection.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", values)
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _serialize(row)


def delete_job(job_id: int) -> bool:
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    return cursor.rowcount > 0


def job_stats() -> dict[str, Any]:
    with _connect() as connection:
        rows = connection.execute("SELECT status, discovered_at FROM jobs WHERE archived = 0").fetchall()
        archived_count = connection.execute("SELECT COUNT(*) FROM jobs WHERE archived = 1").fetchone()[0]
    today = datetime.now(timezone.utc).date().isoformat()
    stages = {status: 0 for status in JOB_STATUSES}
    found_today = 0
    for row in rows:
        if row["status"] in stages:
            stages[row["status"]] += 1
        if (row["discovered_at"] or "").startswith(today):
            found_today += 1
    total = len(rows)
    interviews = stages["Собеседование"] + stages["Оффер"]
    return {
        "total": total,
        "found_today": found_today,
        "archived": int(archived_count),
        "applied": stages["Откликнулся"],
        "replied": stages["Ответили"],
        "interviews": stages["Собеседование"],
        "offers": stages["Оффер"],
        "stages": stages,
        "conversion": round(interviews / total * 100) if total else 0,
    }


def get_job_settings() -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM job_settings WHERE id = 1").fetchone()
    if row is None:
        return {
            "sources": list(DEFAULT_SETTINGS.sources),
            "keywords": list(DEFAULT_SETTINGS.keywords),
            "excluded_keywords": list(DEFAULT_SETTINGS.excluded_keywords),
            "telegram_channels": list(DEFAULT_SETTINGS.telegram_channels),
            "area": DEFAULT_SETTINGS.area,
            "salary_min": DEFAULT_SETTINGS.salary_min,
            "remote_only": DEFAULT_SETTINGS.remote_only,
            "per_source_limit": DEFAULT_SETTINGS.per_source_limit,
        }
    return {
        "sources": _json_list(row["sources_json"]) or list(DEFAULT_SETTINGS.sources),
        "keywords": _json_list(row["keywords_json"]),
        "excluded_keywords": _json_list(row["excluded_keywords_json"]),
        "telegram_channels": _json_list(row["telegram_channels_json"]),
        "area": row["area"] or "Россия",
        "salary_min": int(row["salary_min"] or 0),
        "remote_only": bool(row["remote_only"]),
        "per_source_limit": int(row["per_source_limit"] or 50),
        "updated_at": row["updated_at"],
    }


def save_job_settings(settings: JobSettings) -> dict[str, Any]:
    channels = [channel.strip().lstrip("@") for channel in settings.telegram_channels if channel.strip()]
    payload = (
        json.dumps(list(settings.sources), ensure_ascii=False),
        json.dumps([word.strip() for word in settings.keywords if word.strip()], ensure_ascii=False),
        json.dumps([word.strip() for word in settings.excluded_keywords if word.strip()], ensure_ascii=False),
        json.dumps(channels, ensure_ascii=False),
        settings.area.strip() or "Россия",
        max(0, int(settings.salary_min)),
        1 if settings.remote_only else 0,
        max(1, min(int(settings.per_source_limit), 100)),
        _now(),
    )
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO job_settings (
                id, sources_json, keywords_json, excluded_keywords_json, telegram_channels_json,
                area, salary_min, remote_only, per_source_limit, updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                sources_json = excluded.sources_json,
                keywords_json = excluded.keywords_json,
                excluded_keywords_json = excluded.excluded_keywords_json,
                telegram_channels_json = excluded.telegram_channels_json,
                area = excluded.area,
                salary_min = excluded.salary_min,
                remote_only = excluded.remote_only,
                per_source_limit = excluded.per_source_limit,
                updated_at = excluded.updated_at
            """,
            payload,
        )
    return get_job_settings()


def record_job_source_check(source: str, status: str, found_count: int, error: str = "") -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO job_source_checks (source, status, checked_at, found_count, error)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                status = excluded.status, checked_at = excluded.checked_at,
                found_count = excluded.found_count, error = excluded.error
            """,
            (source, status, _now(), int(found_count), error[:400]),
        )


def list_job_source_statuses() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM job_source_checks").fetchall()
    known = {row["source"]: dict(row) for row in rows}
    return [
        {
            "source": source,
            "status": known.get(source, {}).get("status", "idle"),
            "checked_at": known.get(source, {}).get("checked_at", ""),
            "found_count": int(known.get(source, {}).get("found_count", 0) or 0),
            "error": known.get(source, {}).get("error", ""),
        }
        for source in JOB_SOURCES
    ]


def record_job_run(
    run_id: str,
    started_at: str,
    status: str,
    inserted: int,
    duplicates: int,
    sources: list[str],
    message: str = "",
    error: str = "",
) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO job_runs (id, started_at, finished_at, status, inserted_count, duplicate_count, sources_json, message, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                finished_at = excluded.finished_at, status = excluded.status,
                inserted_count = excluded.inserted_count, duplicate_count = excluded.duplicate_count,
                sources_json = excluded.sources_json, message = excluded.message, error = excluded.error
            """,
            (run_id, started_at, _now(), status, int(inserted), int(duplicates),
             json.dumps(sources, ensure_ascii=False), message[:400], error[:400]),
        )


def list_job_runs(limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM job_runs ORDER BY started_at DESC LIMIT ?", (max(1, min(limit, 100)),)
        ).fetchall()
    return [
        {
            "id": row["id"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "status": row["status"],
            "inserted_count": int(row["inserted_count"]),
            "duplicate_count": int(row["duplicate_count"]),
            "sources": _json_list(row["sources_json"]),
            "message": row["message"],
            "error": row["error"],
        }
        for row in rows
    ]
