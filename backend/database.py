from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .lead_utils import (
    LEAD_SCORE_MAX,
    business_identity_key,
    calculate_lead_score,
    contacts_from_lead,
    direct_contact_types,
    is_real_website,
    normalize_business_text,
    normalize_domain,
    normalize_phone,
)
from .freelance.models import FREELANCE_SOURCES, FREELANCE_STATUSES, FreelanceOrder, FreelanceOrderFilters, FreelanceSettings


DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = Path(os.getenv("SEMIXCRM_DB_PATH", str(DATA_DIR / "semixcrm.sqlite3")))
DEFAULT_SETTINGS = {
    "city": "Москва",
    "niches": ["салоны красоты", "стоматологии", "автосервисы"],
    "sources": ["2gis"],
    "limit": 10,
    "start_page": 1,
}
STATUS_PRIORITY = {"Новый": 0, "Написал": 1, "Ответили": 2, "Созвон": 3, "КП": 4, "Закрыто": 5, "Отказ": 1}


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                city TEXT NOT NULL,
                niche TEXT NOT NULL,
                name TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                rating REAL,
                reviews INTEGER,
                card_url TEXT NOT NULL DEFAULT '',
                social_url TEXT NOT NULL DEFAULT '',
                branch_count INTEGER,
                status TEXT NOT NULL DEFAULT 'Новый',
                next_step TEXT NOT NULL DEFAULT 'Написать владельцу',
                pain TEXT NOT NULL DEFAULT '',
                match_score INTEGER NOT NULL DEFAULT 0,
                lead_score INTEGER NOT NULL DEFAULT 0,
                lead_score_reasons_json TEXT NOT NULL DEFAULT '[]',
                contacts_json TEXT NOT NULL DEFAULT '[]',
                dedupe_key TEXT NOT NULL DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,
                archived_at TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        connection.execute("DROP INDEX IF EXISTS clients_identity_idx")
        _ensure_column(connection, "clients", "lead_score", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "clients", "lead_score_reasons_json", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "clients", "contacts_json", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "clients", "dedupe_key", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "clients", "archived", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "clients", "archived_at", "TEXT NOT NULL DEFAULT ''")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS parser_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                city TEXT NOT NULL,
                niches_json TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                limit_count INTEGER NOT NULL,
                start_page INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS parser_runs (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                city TEXT NOT NULL,
                niche TEXT NOT NULL,
                source TEXT NOT NULL,
                limit_count INTEGER NOT NULL,
                start_page INTEGER NOT NULL DEFAULT 1,
                found_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        _ensure_column(connection, "parser_runs", "skipped_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "parser_runs", "parsed_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "parser_settings", "start_page", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(connection, "parser_runs", "start_page", "INTEGER NOT NULL DEFAULT 1")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS parser_run_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES parser_runs(id) ON DELETE CASCADE,
                client_id INTEGER,
                outcome TEXT NOT NULL CHECK (outcome IN ('inserted', 'duplicate')),
                position INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_date TEXT NOT NULL,
                title TEXT NOT NULL,
                task_time TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'task' CHECK (kind IN ('task', 'meeting')),
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_day_notes (
                day_date TEXT PRIMARY KEY,
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_weeks (
                week_start TEXT PRIMARY KEY,
                summary TEXT NOT NULL DEFAULT '',
                goals_json TEXT NOT NULL DEFAULT '[]',
                focus TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS freelance_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                customer TEXT NOT NULL DEFAULT '',
                categories_json TEXT NOT NULL DEFAULT '[]',
                tags_json TEXT NOT NULL DEFAULT '[]',
                budget_min INTEGER,
                budget_max INTEGER,
                currency TEXT NOT NULL DEFAULT 'RUB',
                budget_text TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                discovered_at TEXT NOT NULL,
                relevance INTEGER NOT NULL DEFAULT 0,
                relevance_reasons_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'Новый',
                next_step TEXT NOT NULL DEFAULT 'Изучить заказ',
                note TEXT NOT NULL DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS freelance_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                sources_json TEXT NOT NULL,
                keywords_json TEXT NOT NULL DEFAULT '[]',
                excluded_keywords_json TEXT NOT NULL DEFAULT '[]',
                categories_json TEXT NOT NULL DEFAULT '[]',
                min_budget INTEGER NOT NULL DEFAULT 0,
                interval_seconds INTEGER NOT NULL DEFAULT 60,
                sniper_enabled INTEGER NOT NULL DEFAULT 0,
                telegram_enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS freelance_source_checks (
                source TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                order_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                auth_required INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS freelance_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                sent_at TEXT,
                error TEXT NOT NULL DEFAULT '',
                UNIQUE(source, external_id, chat_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS freelance_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                status TEXT NOT NULL,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                source_count INTEGER NOT NULL DEFAULT 0,
                sources_json TEXT NOT NULL DEFAULT '[]',
                error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS freelance_run_orders (
                run_id INTEGER NOT NULL REFERENCES freelance_runs(id) ON DELETE CASCADE,
                order_id INTEGER NOT NULL REFERENCES freelance_orders(id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                PRIMARY KEY (run_id, order_id)
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS schedule_tasks_date_idx ON schedule_tasks(task_date)")
        connection.execute("CREATE INDEX IF NOT EXISTS freelance_orders_published_idx ON freelance_orders(published_at)")
        _migrate_and_deduplicate_clients(connection)
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS clients_dedupe_idx ON clients(dedupe_key)")
        existing = connection.execute("SELECT id FROM parser_settings WHERE id = 1").fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO parser_settings (id, city, niches_json, sources_json, limit_count, start_page, updated_at) VALUES (1, ?, ?, ?, ?, ?, ?)",
                (
                    DEFAULT_SETTINGS["city"],
                    json.dumps(DEFAULT_SETTINGS["niches"], ensure_ascii=False),
                    json.dumps(DEFAULT_SETTINGS["sources"], ensure_ascii=False),
                    DEFAULT_SETTINGS["limit"],
                    DEFAULT_SETTINGS["start_page"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


def _migrate_and_deduplicate_clients(connection: sqlite3.Connection) -> None:
    rows = [dict(row) for row in connection.execute("SELECT * FROM clients ORDER BY id")]
    keepers: dict[str, dict[str, Any]] = {}
    duplicate_ids: list[int] = []
    for row in rows:
        row["contacts"] = _json_list(row.get("contacts_json", "[]"), [])
        key = business_identity_key(row)
        row["dedupe_key"] = key
        existing = keepers.get(key)
        if existing is None:
            keepers[key] = row
            continue
        survivor, duplicate = (row, existing) if _row_quality(row) > _row_quality(existing) else (existing, row)
        merged = _merge_client_rows(survivor, duplicate)
        keepers[key] = merged
        duplicate_ids.append(int(duplicate["id"]))

    for row in keepers.values():
        score, reasons, match_score = calculate_lead_score(row)
        contacts = contacts_from_lead(row)
        has_real_website = is_real_website(row.get("website"))
        direct_channels = direct_contact_types(row)
        row["pain"] = (
            "Есть канал для контакта, но нет сайта — хороший кандидат для первого сообщения."
            if direct_channels and not has_real_website
            else "Нет сайта — часть заявок уходит к конкурентам."
            if not has_real_website
            else "Можно усилить онлайн-заявки и автоматизацию."
        )
        existing_tags = [tag for tag in _json_list(row.get("tags_json"), []) if tag not in {"Сайт", "Аудит сайта"}]
        row["tags_json"] = json.dumps(list(dict.fromkeys(["Сайт" if not has_real_website else "Аудит сайта", "CRM", "Автоматизация", *existing_tags])), ensure_ascii=False)
        connection.execute(
            """
            UPDATE clients SET created_at = ?, source = ?, city = ?, niche = ?, name = ?, address = ?,
                phone = ?, website = ?, rating = ?, reviews = ?, card_url = ?, social_url = ?,
                branch_count = ?, status = ?, next_step = ?, pain = ?, match_score = ?, lead_score = ?,
                lead_score_reasons_json = ?, contacts_json = ?, dedupe_key = ?, archived = ?, archived_at = ?, tags_json = ?
            WHERE id = ?
            """,
            (
                row.get("created_at") or datetime.now(timezone.utc).isoformat(), row.get("source") or "2GIS",
                row.get("city") or "", row.get("niche") or "Бизнес", row.get("name") or "Без названия",
                row.get("address") or "", row.get("phone") or "", row.get("website") or "", row.get("rating"),
                row.get("reviews"), row.get("card_url") or "", row.get("social_url") or "", row.get("branch_count"),
                row.get("status") or "Новый", row.get("next_step") or "Написать владельцу", row.get("pain") or "",
                match_score, score, json.dumps(reasons, ensure_ascii=False), json.dumps(contacts, ensure_ascii=False),
                row["dedupe_key"], int(row.get("archived") or 0), row.get("archived_at") or "", row.get("tags_json") or "[]",
                row["id"],
            ),
        )
    if duplicate_ids:
        connection.executemany("DELETE FROM clients WHERE id = ?", [(client_id,) for client_id in duplicate_ids])


def _row_quality(row: dict[str, Any]) -> tuple[int, ...]:
    return (
        1 if row.get("phone") else 0,
        1 if row.get("address") else 0,
        1 if row.get("card_url") else 0,
        len(contacts_from_lead(row)),
        1 if row.get("website") else 0,
        int(row.get("reviews") or 0),
    )


def _merge_client_rows(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for field in ("address", "phone", "website", "card_url", "social_url", "pain"):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    for field in ("rating", "reviews", "branch_count"):
        if merged.get(field) is None and secondary.get(field) is not None:
            merged[field] = secondary[field]
    merged["contacts"] = contacts_from_lead({**merged, "contacts": contacts_from_lead(primary) + contacts_from_lead(secondary)})
    if STATUS_PRIORITY.get(str(secondary.get("status")), 0) > STATUS_PRIORITY.get(str(merged.get("status")), 0):
        merged["status"] = secondary.get("status")
        merged["next_step"] = secondary.get("next_step")
    merged["archived"] = 1 if primary.get("archived") and secondary.get("archived") else 0
    merged["archived_at"] = primary.get("archived_at") or secondary.get("archived_at") or ""
    return merged


def _json_list(value: Any, fallback: list[Any]) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _schedule_date(value: str) -> str:
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except (TypeError, ValueError) as error:
        raise ValueError("Дата должна быть в формате YYYY-MM-DD") from error


def _schedule_week_start(value: str) -> str:
    parsed = date.fromisoformat(_schedule_date(value))
    return (parsed - timedelta(days=parsed.weekday())).isoformat()


def _serialize_schedule_task(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "date": row["task_date"],
        "title": row["title"],
        "time": row["task_time"] or "",
        "kind": row["kind"] or "task",
        "done": bool(row["done"]),
    }


def create_schedule_task(task_date: str, title: str, task_time: str = "", kind: str = "task") -> dict[str, Any]:
    normalized_date = _schedule_date(task_date)
    normalized_title = str(title or "").strip()
    normalized_time = str(task_time or "").strip()
    normalized_kind = str(kind or "task").strip().lower()
    if not normalized_title:
        raise ValueError("Введите название задачи")
    if len(normalized_title) > 240:
        raise ValueError("Название задачи слишком длинное")
    if normalized_kind not in {"task", "meeting"}:
        raise ValueError("Тип записи должен быть task или meeting")
    if normalized_time:
        try:
            datetime.strptime(normalized_time, "%H:%M")
        except ValueError as error:
            raise ValueError("Время должно быть в формате HH:MM") from error
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO schedule_tasks (task_date, title, task_time, kind, done, created_at, updated_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
            (normalized_date, normalized_title, normalized_time, normalized_kind, now, now),
        )
        row = connection.execute("SELECT * FROM schedule_tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _serialize_schedule_task(row)


def update_schedule_task(
    task_id: int,
    title: str | None = None,
    task_date: str | None = None,
    task_time: str | None = None,
    kind: str | None = None,
    done: bool | None = None,
) -> dict[str, Any] | None:
    changes: dict[str, Any] = {}
    if title is not None:
        normalized_title = str(title).strip()
        if not normalized_title:
            raise ValueError("Введите название задачи")
        changes["title"] = normalized_title
    if task_date is not None:
        changes["task_date"] = _schedule_date(task_date)
    if task_time is not None:
        normalized_time = str(task_time).strip()
        if normalized_time:
            try:
                datetime.strptime(normalized_time, "%H:%M")
            except ValueError as error:
                raise ValueError("Время должно быть в формате HH:MM") from error
        changes["task_time"] = normalized_time
    if kind is not None:
        normalized_kind = str(kind).strip().lower()
        if normalized_kind not in {"task", "meeting"}:
            raise ValueError("Тип записи должен быть task или meeting")
        changes["kind"] = normalized_kind
    if done is not None:
        changes["done"] = int(done)
    if not changes:
        with _connect() as connection:
            row = connection.execute("SELECT * FROM schedule_tasks WHERE id = ?", (task_id,)).fetchone()
        return _serialize_schedule_task(row) if row else None
    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    assignments = ", ".join(f"{field} = ?" for field in changes)
    with _connect() as connection:
        connection.execute(f"UPDATE schedule_tasks SET {assignments} WHERE id = ?", (*changes.values(), task_id))
        row = connection.execute("SELECT * FROM schedule_tasks WHERE id = ?", (task_id,)).fetchone()
    return _serialize_schedule_task(row) if row else None


def delete_schedule_task(task_id: int) -> bool:
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM schedule_tasks WHERE id = ?", (task_id,))
    return cursor.rowcount > 0


def save_schedule_note(day_date: str, note: str) -> dict[str, str]:
    normalized_date = _schedule_date(day_date)
    normalized_note = str(note or "").strip()[:2000]
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        if normalized_note:
            connection.execute(
                "INSERT INTO schedule_day_notes (day_date, note, updated_at) VALUES (?, ?, ?) ON CONFLICT(day_date) DO UPDATE SET note = excluded.note, updated_at = excluded.updated_at",
                (normalized_date, normalized_note, now),
            )
        else:
            connection.execute("DELETE FROM schedule_day_notes WHERE day_date = ?", (normalized_date,))
    return {"date": normalized_date, "note": normalized_note}


def save_schedule_week(week_start: str, summary: str, goals: list[dict[str, Any]], focus: str = "") -> dict[str, Any]:
    normalized_week = _schedule_week_start(week_start)
    cleaned_goals: list[dict[str, Any]] = []
    for goal in goals if isinstance(goals, list) else []:
        if not isinstance(goal, dict):
            continue
        title = str(goal.get("title") or "").strip()
        if title:
            cleaned_goals.append({"title": title[:160], "done": bool(goal.get("done"))})
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute(
            "INSERT INTO schedule_weeks (week_start, summary, goals_json, focus, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(week_start) DO UPDATE SET summary = excluded.summary, goals_json = excluded.goals_json, focus = excluded.focus, updated_at = excluded.updated_at",
            (normalized_week, str(summary or "").strip()[:2000], json.dumps(cleaned_goals, ensure_ascii=False), str(focus or "").strip()[:160], now),
        )
    return {"week_start": normalized_week, "summary": str(summary or "").strip()[:2000], "goals": cleaned_goals, "focus": str(focus or "").strip()[:160]}


def get_schedule(week_start: str) -> dict[str, Any]:
    normalized_week = _schedule_week_start(week_start)
    start_date = date.fromisoformat(normalized_week)
    end_date = start_date + timedelta(days=6)
    upcoming_end = end_date + timedelta(days=14)
    with _connect() as connection:
        task_rows = connection.execute(
            "SELECT * FROM schedule_tasks WHERE task_date BETWEEN ? AND ? ORDER BY task_date, CASE WHEN task_time = '' THEN '99:99' ELSE task_time END, id",
            (normalized_week, end_date.isoformat()),
        ).fetchall()
        upcoming_rows = connection.execute(
            "SELECT * FROM schedule_tasks WHERE task_date BETWEEN ? AND ? AND done = 0 ORDER BY task_date, CASE WHEN task_time = '' THEN '99:99' ELSE task_time END, id LIMIT 12",
            (normalized_week, upcoming_end.isoformat()),
        ).fetchall()
        notes_rows = connection.execute(
            "SELECT day_date, note FROM schedule_day_notes WHERE day_date BETWEEN ? AND ?",
            (normalized_week, end_date.isoformat()),
        ).fetchall()
        week_row = connection.execute("SELECT * FROM schedule_weeks WHERE week_start = ?", (normalized_week,)).fetchone()
        past_rows = connection.execute(
            "SELECT DISTINCT date(task_date, '-' || ((CAST(strftime('%w', task_date) AS INTEGER) + 6) % 7) || ' days') AS week_start FROM schedule_tasks WHERE task_date < ? ORDER BY week_start DESC LIMIT 3",
            (normalized_week,),
        ).fetchall()
    tasks = [_serialize_schedule_task(row) for row in task_rows]
    upcoming = [_serialize_schedule_task(row) for row in upcoming_rows]
    stats_total = len(tasks)
    stats_done = sum(1 for task in tasks if task["done"])
    return {
        "week_start": normalized_week,
        "week_end": end_date.isoformat(),
        "tasks": tasks,
        "notes": {row["day_date"]: row["note"] for row in notes_rows},
        "summary": str(week_row["summary"] if week_row else ""),
        "goals": _json_list(week_row["goals_json"], []) if week_row else [],
        "focus": str(week_row["focus"] if week_row else ""),
        "stats": {
            "total": stats_total,
            "done": stats_done,
            "meetings": sum(1 for task in tasks if task["kind"] == "meeting"),
            "completion_percent": round(stats_done / stats_total * 100) if stats_total else 0,
        },
        "upcoming": upcoming,
        "past_weeks": [row["week_start"] for row in past_rows if row["week_start"]],
    }


def _freelance_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _freelance_json_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _json_list(value, []) if str(item).strip()]


def _freelance_key(order: FreelanceOrder) -> str:
    source = str(order.source or "manual").strip().lower()
    external_id = str(order.external_id or "").strip()
    fallback = order.url.strip() or f"{order.title.strip().casefold()}|{order.published_at.strip()}"
    return f"{source}:{external_id or fallback}"


def _serialize_freelance_order(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    return {
        "id": int(item["id"]),
        "source": item["source"],
        "external_id": item["external_id"],
        "title": item["title"],
        "description": item["description"] or "",
        "url": item["url"] or "",
        "customer": item["customer"] or "",
        "categories": _freelance_json_list(item["categories_json"]),
        "tags": _freelance_json_list(item["tags_json"]),
        "budget_min": item["budget_min"],
        "budget_max": item["budget_max"],
        "currency": item["currency"] or "RUB",
        "budget_text": item["budget_text"] or "",
        "published_at": item["published_at"] or "",
        "discovered_at": item["discovered_at"] or "",
        "relevance": int(item["relevance"] or 0),
        "relevance_reasons": _freelance_json_list(item["relevance_reasons_json"]),
        "status": item["status"] or "Новый",
        "next_step": item["next_step"] or "Изучить заказ",
        "note": item["note"] or "",
        "archived": bool(item["archived"]),
    }


def create_freelance_order(order: FreelanceOrder) -> dict[str, Any]:
    source = str(order.source or "manual").strip().lower()
    if not order.title.strip():
        raise ValueError("Название заказа обязательно")
    if source not in (*FREELANCE_SOURCES, "manual"):
        raise ValueError("Неизвестный источник заказа")
    status = order.status if order.status in FREELANCE_STATUSES else "Новый"
    now = _freelance_now()
    dedupe_key = _freelance_key(FreelanceOrder(**{**order.__dict__, "source": source}))
    values = (
        source, str(order.external_id or "").strip(), dedupe_key, order.title.strip(), order.description.strip(),
        order.url.strip(), order.customer.strip(), json.dumps(list(order.categories), ensure_ascii=False),
        json.dumps(list(order.tags), ensure_ascii=False), order.budget_min, order.budget_max, order.currency.strip() or "RUB",
        order.budget_text.strip(), order.published_at.strip(), order.discovered_at.strip() or now, max(0, min(int(order.relevance), 100)),
        json.dumps(list(order.relevance_reasons), ensure_ascii=False), status, order.next_step.strip() or "Изучить заказ",
        order.note.strip(), int(order.archived), now, now,
    )
    with _connect() as connection:
        existing = connection.execute("SELECT * FROM freelance_orders WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
        if existing:
            connection.execute(
                """UPDATE freelance_orders SET title = ?, description = ?, url = ?, customer = ?, categories_json = ?, tags_json = ?,
                    budget_min = ?, budget_max = ?, currency = ?, budget_text = ?, published_at = ?, relevance = ?,
                    relevance_reasons_json = ?, updated_at = ? WHERE id = ?""",
                (values[3], values[4], values[5], values[6], values[7], values[8], values[9], values[10], values[11], values[12], values[13], values[15], values[16], now, existing["id"]),
            )
            row = connection.execute("SELECT * FROM freelance_orders WHERE id = ?", (existing["id"],)).fetchone()
            return _serialize_freelance_order(row)
        cursor = connection.execute(
            """INSERT INTO freelance_orders (source, external_id, dedupe_key, title, description, url, customer, categories_json, tags_json,
                budget_min, budget_max, currency, budget_text, published_at, discovered_at, relevance, relevance_reasons_json, status,
                next_step, note, archived, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        row = connection.execute("SELECT * FROM freelance_orders WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _serialize_freelance_order(row)


def freelance_order_exists(order: FreelanceOrder) -> bool:
    with _connect() as connection:
        row = connection.execute("SELECT 1 FROM freelance_orders WHERE dedupe_key = ?", (_freelance_key(order),)).fetchone()
    return row is not None


def telegram_allowed_chat_id() -> str:
    return os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip()


def list_freelance_orders(filters: FreelanceOrderFilters) -> list[dict[str, Any]]:
    clauses = ["archived = ?"]
    params: list[Any] = [0 if not filters.include_archived else 1]
    if filters.source:
        clauses.append("source = ?")
        params.append(filters.source.strip().lower())
    if filters.status:
        clauses.append("status = ?")
        params.append(filters.status)
    if filters.category:
        clauses.append("(categories_json LIKE ? OR tags_json LIKE ?)")
        needle = f"%{filters.category.strip()}%"
        params.extend([needle, needle])
    if filters.min_budget is not None:
        clauses.append("COALESCE(budget_max, budget_min, 0) >= ?")
        params.append(max(0, filters.min_budget))
    if filters.query.strip():
        clauses.append("(title LIKE ? OR description LIKE ? OR customer LIKE ? OR tags_json LIKE ? OR categories_json LIKE ?)")
        needle = f"%{filters.query.strip()}%"
        params.extend([needle] * 5)
    order_by = {
        "newest": "COALESCE(published_at, discovered_at) DESC, id DESC",
        "budget": "COALESCE(budget_max, budget_min, 0) DESC, id DESC",
        "relevance": "relevance DESC, COALESCE(published_at, discovered_at) DESC, id DESC",
    }.get(filters.sort, "relevance DESC, COALESCE(published_at, discovered_at) DESC, id DESC")
    with _connect() as connection:
        rows = connection.execute(f"SELECT * FROM freelance_orders WHERE {' AND '.join(clauses)} ORDER BY {order_by}", params).fetchall()
    return [_serialize_freelance_order(row) for row in rows]


def get_freelance_order(order_id: int) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM freelance_orders WHERE id = ?", (order_id,)).fetchone()
    return _serialize_freelance_order(row) if row else None


def update_freelance_order(order_id: int, **changes: Any) -> dict[str, Any] | None:
    allowed = {"status", "next_step", "note", "archived", "relevance", "relevance_reasons_json"}
    values = {key: value for key, value in changes.items() if key in allowed and value is not None}
    if "status" in values and values["status"] not in FREELANCE_STATUSES:
        raise ValueError("Неизвестный статус заказа")
    if not values:
        return get_freelance_order(order_id)
    if "archived" in values:
        values["archived"] = int(bool(values["archived"]))
    values["updated_at"] = _freelance_now()
    assignments = ", ".join(f"{field} = ?" for field in values)
    with _connect() as connection:
        connection.execute(f"UPDATE freelance_orders SET {assignments} WHERE id = ?", (*values.values(), order_id))
        row = connection.execute("SELECT * FROM freelance_orders WHERE id = ?", (order_id,)).fetchone()
    return _serialize_freelance_order(row) if row else None


def archive_freelance_order(order_id: int) -> bool:
    return update_freelance_order(order_id, archived=True) is not None


def freelance_stats() -> dict[str, Any]:
    with _connect() as connection:
        rows = connection.execute("SELECT status, discovered_at FROM freelance_orders WHERE archived = 0").fetchall()
    today = datetime.now(timezone.utc).date().isoformat()
    stages = {status: 0 for status in FREELANCE_STATUSES}
    for row in rows:
        if row["status"] in stages:
            stages[row["status"]] += 1
    return {
        "total": len(rows),
        "responded": stages["Откликнулся"],
        "replied": stages["Ответили"],
        "in_progress": stages["В работе"],
        "new_today": sum(1 for row in rows if str(row["discovered_at"]).startswith(today)),
        "stages": stages,
    }


def get_freelance_settings() -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM freelance_settings WHERE id = 1").fetchone()
    if row is None:
        return {
            "sources": list(FREELANCE_SOURCES), "keywords": [], "excluded_keywords": [], "categories": [],
            "min_budget": 0, "interval_seconds": 60, "sniper_enabled": False, "telegram_enabled": False,
        }
    return {
        "sources": _freelance_json_list(row["sources_json"]), "keywords": _freelance_json_list(row["keywords_json"]),
        "excluded_keywords": _freelance_json_list(row["excluded_keywords_json"]), "categories": _freelance_json_list(row["categories_json"]),
        "min_budget": int(row["min_budget"] or 0), "interval_seconds": int(row["interval_seconds"] or 60),
        "sniper_enabled": bool(row["sniper_enabled"]), "telegram_enabled": bool(row["telegram_enabled"]),
        "updated_at": row["updated_at"],
    }


def save_freelance_settings(settings: FreelanceSettings) -> dict[str, Any]:
    sources = [source for source in dict.fromkeys(settings.sources) if source in FREELANCE_SOURCES]
    if not sources:
        raise ValueError("Выберите хотя бы один источник")
    now = _freelance_now()
    with _connect() as connection:
        connection.execute(
            """INSERT INTO freelance_settings (id, sources_json, keywords_json, excluded_keywords_json, categories_json, min_budget, interval_seconds, sniper_enabled, telegram_enabled, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET sources_json = excluded.sources_json, keywords_json = excluded.keywords_json,
            excluded_keywords_json = excluded.excluded_keywords_json, categories_json = excluded.categories_json, min_budget = excluded.min_budget,
            interval_seconds = excluded.interval_seconds, sniper_enabled = excluded.sniper_enabled, telegram_enabled = excluded.telegram_enabled, updated_at = excluded.updated_at""",
            (json.dumps(sources, ensure_ascii=False), json.dumps(list(dict.fromkeys(settings.keywords)), ensure_ascii=False), json.dumps(list(dict.fromkeys(settings.excluded_keywords)), ensure_ascii=False), json.dumps(list(dict.fromkeys(settings.categories)), ensure_ascii=False), max(0, settings.min_budget), max(30, min(settings.interval_seconds, 3600)), int(settings.sniper_enabled), int(settings.telegram_enabled), now),
        )
    return get_freelance_settings()


def record_source_check(status: dict[str, Any]) -> None:
    with _connect() as connection:
        connection.execute(
            """INSERT INTO freelance_source_checks (source, status, checked_at, order_count, error, auth_required) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET status = excluded.status, checked_at = excluded.checked_at, order_count = excluded.order_count, error = excluded.error, auth_required = excluded.auth_required""",
            (status["source"], status.get("status", "unknown"), status.get("checked_at") or _freelance_now(), int(status.get("order_count") or 0), status.get("error") or "", int(bool(status.get("auth_required")))),
        )


def list_source_statuses() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM freelance_source_checks ORDER BY source").fetchall()
    return [{**dict(row), "auth_required": bool(row["auth_required"])} for row in rows]


def record_freelance_run(run: dict[str, Any], order_ids: list[int] | None = None) -> int:
    with _connect() as connection:
        cursor = connection.execute(
            """INSERT INTO freelance_runs (started_at, finished_at, status, inserted_count, duplicate_count, source_count, sources_json, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.get("started_at") or _freelance_now(),
                run.get("finished_at") or _freelance_now(),
                run.get("status") or "done",
                int(run.get("inserted") or 0),
                int(run.get("duplicates") or 0),
                int(run.get("source_count") or len(run.get("sources") or {})),
                json.dumps(run.get("sources") or {}, ensure_ascii=False),
                run.get("error") or "",
            ),
        )
        run_id = int(cursor.lastrowid)
        for order_id in dict.fromkeys(order_ids or []):
            row = connection.execute("SELECT source, external_id FROM freelance_orders WHERE id = ?", (order_id,)).fetchone()
            if row:
                connection.execute(
                    "INSERT OR IGNORE INTO freelance_run_orders (run_id, order_id, source, external_id) VALUES (?, ?, ?, ?)",
                    (run_id, order_id, row["source"], row["external_id"]),
                )
    return run_id


def list_freelance_runs(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM freelance_runs ORDER BY id DESC LIMIT ?", (safe_limit,)).fetchall()
        counts = connection.execute("SELECT run_id, COUNT(*) AS order_count FROM freelance_run_orders GROUP BY run_id").fetchall()
    count_by_run = {int(row["run_id"]): int(row["order_count"]) for row in counts}
    return [{**dict(row), "sources": json.loads(row["sources_json"] or "{}"), "order_count": count_by_run.get(int(row["id"]), 0)} for row in rows]


def get_freelance_run(run_id: int) -> dict[str, Any] | None:
    with _connect() as connection:
        run = connection.execute("SELECT * FROM freelance_runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            return None
        orders = connection.execute(
            """SELECT freelance_orders.* FROM freelance_run_orders
            JOIN freelance_orders ON freelance_orders.id = freelance_run_orders.order_id
            WHERE freelance_run_orders.run_id = ? ORDER BY freelance_run_orders.order_id""",
            (run_id,),
        ).fetchall()
    return {**dict(run), "sources": json.loads(run["sources_json"] or "{}"), "orders": [_serialize_freelance_order(row) for row in orders]}


def notification_sent(source: str, external_id: str, chat_id: str) -> bool:
    with _connect() as connection:
        row = connection.execute("SELECT 1 FROM freelance_notifications WHERE source = ? AND external_id = ? AND chat_id = ? AND sent_at IS NOT NULL", (source, external_id, chat_id)).fetchone()
    return row is not None


def record_notification(source: str, external_id: str, chat_id: str, error: str = "") -> None:
    with _connect() as connection:
        connection.execute(
            """INSERT INTO freelance_notifications (source, external_id, chat_id, sent_at, error) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, external_id, chat_id) DO UPDATE SET sent_at = excluded.sent_at, error = excluded.error""",
            (source, external_id, chat_id, _freelance_now() if not error else None, error),
        )


def get_parser_settings() -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM parser_settings WHERE id = 1").fetchone()
    if row is None:
        return dict(DEFAULT_SETTINGS)
    return {
        "city": row["city"],
        "niches": [str(item).strip() for item in _json_list(row["niches_json"], DEFAULT_SETTINGS["niches"]) if str(item).strip()],
        "sources": [str(item).strip() for item in _json_list(row["sources_json"], DEFAULT_SETTINGS["sources"]) if str(item).strip()],
        "limit": row["limit_count"],
        "start_page": max(1, int(row["start_page"] or 1)),
        "updated_at": row["updated_at"],
    }


def save_parser_settings(city: str, niches: list[str], sources: list[str], limit: int, start_page: int = 1) -> dict[str, Any]:
    cleaned_niches = list(dict.fromkeys(item.strip() for item in niches if item.strip()))
    cleaned_sources = list(dict.fromkeys(item.strip().lower() for item in sources if item.strip()))
    if not cleaned_niches:
        raise ValueError("Выберите хотя бы одну нишу")
    if not cleaned_sources:
        raise ValueError("Выберите хотя бы один источник")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute(
            "UPDATE parser_settings SET city = ?, niches_json = ?, sources_json = ?, limit_count = ?, start_page = ?, updated_at = ? WHERE id = 1",
            (city.strip(), json.dumps(cleaned_niches, ensure_ascii=False), json.dumps(cleaned_sources, ensure_ascii=False), max(1, min(limit, 50)), max(1, min(int(start_page), 999)), now),
        )
    return get_parser_settings()


def create_parser_run(run_id: str, city: str, niche: str, source: str, limit: int, start_page: int = 1) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO parser_runs (id, started_at, status, city, niche, source, limit_count, start_page) VALUES (?, ?, 'running', ?, ?, ?, ?, ?)",
            (run_id, datetime.now(timezone.utc).isoformat(), city, niche, source, limit, max(1, min(int(start_page), 999))),
        )


def update_parser_run(
    run_id: str,
    status: str,
    found_count: int,
    message: str,
    error: str = "",
    skipped_count: int = 0,
    parsed_count: int | None = None,
) -> None:
    total_parsed = parsed_count if parsed_count is not None else found_count + skipped_count
    with _connect() as connection:
        connection.execute(
            "UPDATE parser_runs SET finished_at = ?, status = ?, found_count = ?, skipped_count = ?, parsed_count = ?, message = ?, error = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), status, found_count, skipped_count, total_parsed, message, error, run_id),
        )


def list_parser_runs(limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT parser_runs.*, COUNT(parser_run_results.id) AS result_count
            FROM parser_runs
            LEFT JOIN parser_run_results ON parser_run_results.run_id = parser_runs.id
            GROUP BY parser_runs.id
            ORDER BY parser_runs.started_at DESC
            LIMIT ?
            """,
            (max(1, min(limit, 100)),),
        ).fetchall()
    return [_serialize_parser_run(row) for row in rows]


def save_parser_run_results(run_id: str, results: list[dict[str, Any]]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for position, result in enumerate(results):
        outcome = str(result.get("outcome") or "")
        if outcome not in {"inserted", "duplicate"}:
            raise ValueError(f"Unknown parser result outcome: {outcome}")
        rows.append((
            run_id,
            int(result["client_id"]) if result.get("client_id") is not None else None,
            outcome,
            position,
            json.dumps(result.get("snapshot") or {}, ensure_ascii=False),
            now,
        ))
    with _connect() as connection:
        connection.execute("DELETE FROM parser_run_results WHERE run_id = ?", (run_id,))
        connection.executemany(
            """
            INSERT INTO parser_run_results (run_id, client_id, outcome, position, snapshot_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def get_parser_run(run_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT parser_runs.*, COUNT(parser_run_results.id) AS result_count
            FROM parser_runs
            LEFT JOIN parser_run_results ON parser_run_results.run_id = parser_runs.id
            WHERE parser_runs.id = ?
            GROUP BY parser_runs.id
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        result_rows = connection.execute(
            "SELECT client_id, outcome, position, snapshot_json, created_at FROM parser_run_results WHERE run_id = ? ORDER BY position",
            (run_id,),
        ).fetchall()
    run = _serialize_parser_run(row)
    run["results"] = [
        {
            "client_id": result["client_id"],
            "outcome": result["outcome"],
            "position": result["position"],
            "created_at": result["created_at"],
            "snapshot": _json_object(result["snapshot_json"]),
        }
        for result in result_rows
    ]
    return run


def _serialize_parser_run(row: sqlite3.Row) -> dict[str, Any]:
    run = dict(row)
    result_count = int(run.get("result_count") or 0)
    run["result_count"] = result_count
    run["parsed_count"] = int(run.get("parsed_count") or 0)
    run["snapshot_available"] = result_count > 0
    return run


def client_stats() -> dict[str, Any]:
    with _connect() as connection:
        rows = connection.execute("SELECT status, created_at FROM clients WHERE archived = 0").fetchall()
    today = datetime.now(timezone.utc).date().isoformat()
    stages = {"Новый": 0, "Написал": 0, "Ответили": 0, "Созвон": 0, "КП": 0, "Закрыто": 0, "Отказ": 0}
    for row in rows:
        if row["status"] in stages:
            stages[row["status"]] += 1
    contacted = len(rows) - stages["Новый"]
    replied = stages["Ответили"] + stages["Созвон"] + stages["КП"] + stages["Закрыто"]
    return {
        "total": len(rows), "contacted": contacted, "replied": replied,
        "calls": stages["Созвон"], "closed": stages["Закрыто"],
        "found_today": sum(1 for row in rows if str(row["created_at"]).startswith(today)),
        "new_today": sum(1 for row in rows if str(row["created_at"]).startswith(today) and row["status"] == "Новый"),
        "stages": stages,
    }


def update_client_status(client_id: int, status: str, next_step: str) -> dict[str, Any] | None:
    with _connect() as connection:
        connection.execute("UPDATE clients SET status = ?, next_step = ? WHERE id = ? AND archived = 0", (status, next_step, client_id))
        row = connection.execute("SELECT * FROM clients WHERE id = ? AND archived = 0", (client_id,)).fetchone()
    return _serialize(row) if row else None


def archive_client(client_id: int) -> bool:
    with _connect() as connection:
        cursor = connection.execute(
            "UPDATE clients SET archived = 1, archived_at = ? WHERE id = ? AND archived = 0",
            (datetime.now(timezone.utc).isoformat(), client_id),
        )
    return cursor.rowcount > 0


def archive_all_clients() -> int:
    with _connect() as connection:
        cursor = connection.execute(
            "UPDATE clients SET archived = 1, archived_at = ? WHERE archived = 0",
            (datetime.now(timezone.utc).isoformat(),),
        )
    return max(0, cursor.rowcount)


def list_archived_clients() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM clients WHERE archived = 1 ORDER BY archived_at DESC, id DESC"
        ).fetchall()
    return [_serialize(row) for row in rows]


def restore_client(client_id: int) -> dict[str, Any] | None:
    with _connect() as connection:
        connection.execute(
            "UPDATE clients SET archived = 0, archived_at = '' WHERE id = ? AND archived = 1",
            (client_id,),
        )
        row = connection.execute("SELECT * FROM clients WHERE id = ? AND archived = 0", (client_id,)).fetchone()
    return _serialize(row) if row else None


def restore_all_clients() -> int:
    with _connect() as connection:
        cursor = connection.execute("UPDATE clients SET archived = 0, archived_at = '' WHERE archived = 1")
    return max(0, cursor.rowcount)


def _serialize(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "created_at": row["created_at"], "source": row["source"], "city": row["city"],
        "niche": row["niche"], "category": row["niche"], "name": row["name"], "address": row["address"],
        "phone": row["phone"], "website": row["website"], "rating": row["rating"], "reviews": row["reviews"],
        "card_url": row["card_url"], "social_url": row["social_url"], "contacts": _json_list(row["contacts_json"], []),
        "branch_count": row["branch_count"], "status": row["status"], "next_step": row["next_step"],
        "pain": row["pain"], "match_score": row["match_score"], "lead_score": row["lead_score"],
        "lead_score_max": LEAD_SCORE_MAX, "lead_score_reasons": _json_list(row["lead_score_reasons_json"], []),
        "tags": _json_list(row["tags_json"], []), "archived": int(row["archived"] or 0), "archived_at": row["archived_at"] or "",
    }


def list_clients() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM clients WHERE archived = 0 ORDER BY lead_score DESC, reviews DESC, id DESC"
        ).fetchall()
    return [_serialize(row) for row in rows]


def insert_clients(leads: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    inserted_count = 0
    duplicate_count = 0
    inserted_ids: list[int] = []
    results: list[dict[str, Any]] = []
    with _connect() as connection:
        for position, incoming in enumerate(leads):
            lead = dict(incoming)
            lead["contacts"] = contacts_from_lead(lead)
            score, reasons, match_score = calculate_lead_score(lead)
            lead["lead_score"] = score
            lead["lead_score_reasons"] = reasons
            lead["match_score"] = match_score
            key = business_identity_key(lead)
            existing = _find_existing(connection, lead, key)
            if existing is not None:
                duplicate_count += 1
                _update_existing(connection, existing, lead, key)
                results.append({"client_id": int(existing["id"]), "outcome": "duplicate", "position": position, "snapshot": _snapshot_from_lead(lead, int(existing["id"]))})
                continue

            cursor = connection.execute(
                """
                INSERT INTO clients (
                    created_at, source, city, niche, name, address, phone, website, rating, reviews,
                    card_url, social_url, contacts_json, branch_count, pain, match_score, lead_score,
                    lead_score_reasons_json, dedupe_key, tags_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now, str(lead.get("source") or "2GIS"), str(lead.get("city") or ""), str(lead.get("niche") or "Бизнес"),
                    str(lead.get("name") or "Без названия").strip(), str(lead.get("address") or "").strip(),
                    str(lead.get("phone") or "").strip(), str(lead.get("website") or "").strip(), lead.get("rating"),
                    lead.get("reviews"), str(lead.get("card_url") or "").strip(), str(lead.get("social_url") or "").strip(),
                    json.dumps(lead["contacts"], ensure_ascii=False), lead.get("branch_count"), str(lead.get("pain") or "").strip(),
                    match_score, score, json.dumps(reasons, ensure_ascii=False), key,
                    json.dumps(lead.get("tags") or [], ensure_ascii=False),
                ),
            )
            inserted_count += 1
            client_id = int(cursor.lastrowid)
            inserted_ids.append(client_id)
            results.append({"client_id": client_id, "outcome": "inserted", "position": position, "snapshot": _snapshot_from_lead(lead, client_id)})

    return {
        "clients": list_clients(), "inserted_count": inserted_count,
        "duplicate_count": duplicate_count, "inserted_ids": inserted_ids, "results": results,
    }


def _snapshot_from_lead(lead: dict[str, Any], client_id: int) -> dict[str, Any]:
    snapshot = dict(lead)
    snapshot["id"] = client_id
    snapshot["category"] = snapshot.get("category") or snapshot.get("niche") or "Business"
    snapshot["status"] = snapshot.get("status") or next(iter(STATUS_PRIORITY))
    snapshot["next_step"] = snapshot.get("next_step") or ""
    snapshot["contacts"] = contacts_from_lead(snapshot)
    snapshot["lead_score_reasons"] = list(snapshot.get("lead_score_reasons") or [])
    snapshot["tags"] = list(snapshot.get("tags") or [])
    return snapshot


def _find_existing(connection: sqlite3.Connection, lead: dict[str, Any], key: str) -> sqlite3.Row | None:
    exact = connection.execute("SELECT * FROM clients WHERE dedupe_key = ?", (key,)).fetchone()
    if exact is not None:
        return exact
    name = normalize_business_text(lead.get("name"))
    city = normalize_business_text(lead.get("city"))
    address = normalize_business_text(lead.get("address"))
    phone = normalize_phone(lead.get("phone"))
    domain = normalize_domain(lead.get("website"))
    for row in connection.execute("SELECT * FROM clients"):
        if phone and phone == normalize_phone(row["phone"]):
            return row
        if domain and domain == normalize_domain(row["website"]):
            return row
        if name and city and name == normalize_business_text(row["name"]) and city == normalize_business_text(row["city"]):
            row_address = normalize_business_text(row["address"])
            if address and row_address and address == row_address:
                return row
            if not address or not row_address:
                return row
    return None


def _update_existing(
    connection: sqlite3.Connection,
    existing: sqlite3.Row,
    lead: dict[str, Any],
    key: str,
) -> None:
    old = dict(existing)
    old["contacts"] = _json_list(old.get("contacts_json", "[]"), [])
    merged = _merge_client_rows(old, lead)
    merged["pain"] = lead.get("pain") or merged.get("pain") or ""
    merged_contacts = contacts_from_lead({**merged, "contacts": old["contacts"] + contacts_from_lead(lead)})
    merged_score_input = {**merged, "contacts": merged_contacts}
    merged_score, merged_reasons, merged_match = calculate_lead_score(merged_score_input)
    old_tags = [tag for tag in _json_list(existing["tags_json"], []) if tag not in {"Сайт", "Аудит сайта"}]
    new_tags = [tag for tag in list(lead.get("tags") or []) if tag not in {"Сайт", "Аудит сайта"}]
    merged_tags = list(dict.fromkeys(["Сайт" if not is_real_website(merged.get("website")) else "Аудит сайта", "CRM", "Автоматизация", *old_tags, *new_tags]))
    connection.execute(
        """
        UPDATE clients SET address = ?, phone = ?, website = ?, rating = ?, reviews = ?, card_url = ?, social_url = ?,
            contacts_json = ?, branch_count = ?, pain = ?, match_score = ?, lead_score = ?, lead_score_reasons_json = ?,
            tags_json = ?, dedupe_key = ? WHERE id = ?
        """,
        (
            merged.get("address") or "", merged.get("phone") or "", merged.get("website") or "", merged.get("rating"),
            max(int(existing["reviews"] or 0), int(lead.get("reviews") or 0)) or None,
            merged.get("card_url") or "", merged.get("social_url") or "", json.dumps(merged_contacts, ensure_ascii=False),
            merged.get("branch_count"), merged.get("pain") or "", merged_match, merged_score,
            json.dumps(merged_reasons, ensure_ascii=False), json.dumps(merged_tags, ensure_ascii=False),
            key, existing["id"],
        ),
    )
