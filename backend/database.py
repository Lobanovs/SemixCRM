from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = Path(os.getenv("SEMIXCRM_DB_PATH", str(DATA_DIR / "semixcrm.sqlite3")))
DEFAULT_SETTINGS = {
    "city": "Москва",
    "niches": ["салоны красоты", "стоматологии", "автосервисы"],
    "sources": ["2gis"],
    "limit": 10,
}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


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
                match_score INTEGER NOT NULL DEFAULT 70,
                tags_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS clients_identity_idx ON clients(name, city, address)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS parser_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                city TEXT NOT NULL,
                niches_json TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                limit_count INTEGER NOT NULL,
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
                found_count INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        existing = connection.execute("SELECT id FROM parser_settings WHERE id = 1").fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO parser_settings (id, city, niches_json, sources_json, limit_count, updated_at) VALUES (1, ?, ?, ?, ?, ?)",
                (
                    DEFAULT_SETTINGS["city"],
                    json.dumps(DEFAULT_SETTINGS["niches"], ensure_ascii=False),
                    json.dumps(DEFAULT_SETTINGS["sources"], ensure_ascii=False),
                    DEFAULT_SETTINGS["limit"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


def _json_list(value: str, fallback: list[str]) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        return [str(item).strip() for item in parsed if str(item).strip()] if isinstance(parsed, list) else fallback
    except json.JSONDecodeError:
        return fallback


def get_parser_settings() -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM parser_settings WHERE id = 1").fetchone()
    if row is None:
        return dict(DEFAULT_SETTINGS)
    return {
        "city": row["city"],
        "niches": _json_list(row["niches_json"], DEFAULT_SETTINGS["niches"]),
        "sources": _json_list(row["sources_json"], DEFAULT_SETTINGS["sources"]),
        "limit": row["limit_count"],
        "updated_at": row["updated_at"],
    }


def save_parser_settings(city: str, niches: list[str], sources: list[str], limit: int) -> dict[str, Any]:
    cleaned_niches = [item.strip() for item in niches if item.strip()]
    cleaned_sources = [item.strip().lower() for item in sources if item.strip()]
    if not cleaned_niches:
        raise ValueError("Добавьте хотя бы одну нишу")
    if not cleaned_sources:
        raise ValueError("Выберите хотя бы один источник")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute(
            "UPDATE parser_settings SET city = ?, niches_json = ?, sources_json = ?, limit_count = ?, updated_at = ? WHERE id = 1",
            (city.strip(), json.dumps(cleaned_niches, ensure_ascii=False), json.dumps(cleaned_sources), max(1, min(limit, 50)), now),
        )
        connection.commit()
    return get_parser_settings()


def create_parser_run(run_id: str, city: str, niche: str, source: str, limit: int) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO parser_runs (id, started_at, status, city, niche, source, limit_count) VALUES (?, ?, 'running', ?, ?, ?, ?)",
            (run_id, datetime.now(timezone.utc).isoformat(), city, niche, source, limit),
        )


def update_parser_run(run_id: str, status: str, found_count: int, message: str, error: str = "") -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE parser_runs SET finished_at = ?, status = ?, found_count = ?, message = ?, error = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), status, found_count, message, error, run_id),
        )


def list_parser_runs(limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM parser_runs ORDER BY started_at DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
    return [dict(row) for row in rows]


def client_stats() -> dict[str, Any]:
    with _connect() as connection:
        rows = connection.execute("SELECT status, created_at FROM clients").fetchall()
    today = datetime.now(timezone.utc).date().isoformat()
    stages = {"Новый": 0, "Написал": 0, "Ответили": 0, "Созвон": 0, "КП": 0, "Закрыто": 0, "Отказ": 0}
    for row in rows:
        if row["status"] in stages:
            stages[row["status"]] += 1
    contacted = len(rows) - stages["Новый"]
    replied = stages["Ответили"] + stages["Созвон"] + stages["КП"] + stages["Закрыто"]
    return {
        "total": len(rows),
        "contacted": contacted,
        "replied": replied,
        "calls": stages["Созвон"],
        "closed": stages["Закрыто"],
        "found_today": sum(1 for row in rows if str(row["created_at"]).startswith(today)),
        "new_today": sum(1 for row in rows if str(row["created_at"]).startswith(today) and row["status"] == "Новый"),
        "stages": stages,
    }


def update_client_status(client_id: int, status: str, next_step: str) -> dict[str, Any] | None:
    with _connect() as connection:
        connection.execute("UPDATE clients SET status = ?, next_step = ? WHERE id = ?", (status, next_step, client_id))
        row = connection.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        connection.commit()
    return _serialize(row) if row else None


def _tags(row: sqlite3.Row) -> list[str]:
    try:
        value = json.loads(row["tags_json"] or "[]")
        return value if isinstance(value, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _serialize(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "source": row["source"],
        "city": row["city"],
        "niche": row["niche"],
        "category": row["niche"],
        "name": row["name"],
        "address": row["address"],
        "phone": row["phone"],
        "website": row["website"],
        "rating": row["rating"],
        "reviews": row["reviews"],
        "card_url": row["card_url"],
        "social_url": row["social_url"],
        "branch_count": row["branch_count"],
        "status": row["status"],
        "next_step": row["next_step"],
        "pain": row["pain"],
        "match_score": row["match_score"],
        "tags": _tags(row),
    }


def list_clients() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM clients ORDER BY match_score DESC, id DESC").fetchall()
    return [_serialize(row) for row in rows]


def insert_clients(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        for lead in leads:
            connection.execute(
                """
                INSERT INTO clients (
                    created_at, source, city, niche, name, address, phone, website,
                    rating, reviews, card_url, social_url, branch_count, pain, match_score, tags_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, city, address) DO UPDATE SET
                    phone=CASE WHEN excluded.phone <> '' THEN excluded.phone ELSE clients.phone END,
                    website=CASE WHEN excluded.website <> '' THEN excluded.website ELSE clients.website END,
                    rating=COALESCE(excluded.rating, clients.rating),
                    reviews=COALESCE(excluded.reviews, clients.reviews),
                    card_url=CASE WHEN excluded.card_url <> '' THEN excluded.card_url ELSE clients.card_url END,
                    social_url=CASE WHEN excluded.social_url <> '' THEN excluded.social_url ELSE clients.social_url END,
                    branch_count=COALESCE(excluded.branch_count, clients.branch_count),
                    pain=CASE WHEN excluded.pain <> '' THEN excluded.pain ELSE clients.pain END,
                    match_score=MAX(clients.match_score, excluded.match_score),
                    tags_json=CASE WHEN excluded.tags_json <> '[]' THEN excluded.tags_json ELSE clients.tags_json END
                """,
                (
                    now,
                    str(lead.get("source") or "2GIS"),
                    str(lead.get("city") or ""),
                    str(lead.get("niche") or "Бизнес"),
                    str(lead.get("name") or "Без названия").strip(),
                    str(lead.get("address") or "").strip(),
                    str(lead.get("phone") or "").strip(),
                    str(lead.get("website") or "").strip(),
                    lead.get("rating"),
                    lead.get("reviews"),
                    str(lead.get("card_url") or "").strip(),
                    str(lead.get("social_url") or "").strip(),
                    lead.get("branch_count"),
                    str(lead.get("pain") or "").strip(),
                    int(lead.get("match_score") or 70),
                    json.dumps(lead.get("tags") or [], ensure_ascii=False),
                ),
            )
        connection.commit()
    return list_clients()
