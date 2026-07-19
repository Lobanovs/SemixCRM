from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "semixcrm.sqlite3"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
