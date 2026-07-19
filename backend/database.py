from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = Path(os.getenv("SEMIXCRM_DB_PATH", str(DATA_DIR / "semixcrm.sqlite3")))
DEFAULT_SETTINGS = {
    "city": "Москва",
    "niches": ["салоны красоты", "стоматологии", "автосервисы"],
    "sources": ["2gis"],
    "limit": 10,
}
STATUS_PRIORITY = {"Новый": 0, "Написал": 1, "Ответили": 2, "Созвон": 3, "КП": 4, "Закрыто": 5, "Отказ": 1}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


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
                skipped_count INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        _ensure_column(connection, "parser_runs", "skipped_count", "INTEGER NOT NULL DEFAULT 0")
        _migrate_and_deduplicate_clients(connection)
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS clients_dedupe_idx ON clients(dedupe_key)")
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
        "updated_at": row["updated_at"],
    }


def save_parser_settings(city: str, niches: list[str], sources: list[str], limit: int) -> dict[str, Any]:
    cleaned_niches = list(dict.fromkeys(item.strip() for item in niches if item.strip()))
    cleaned_sources = list(dict.fromkeys(item.strip().lower() for item in sources if item.strip()))
    if not cleaned_niches:
        raise ValueError("Выберите хотя бы одну нишу")
    if not cleaned_sources:
        raise ValueError("Выберите хотя бы один источник")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute(
            "UPDATE parser_settings SET city = ?, niches_json = ?, sources_json = ?, limit_count = ?, updated_at = ? WHERE id = 1",
            (city.strip(), json.dumps(cleaned_niches, ensure_ascii=False), json.dumps(cleaned_sources, ensure_ascii=False), max(1, min(limit, 50)), now),
        )
    return get_parser_settings()


def create_parser_run(run_id: str, city: str, niche: str, source: str, limit: int) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO parser_runs (id, started_at, status, city, niche, source, limit_count) VALUES (?, ?, 'running', ?, ?, ?, ?)",
            (run_id, datetime.now(timezone.utc).isoformat(), city, niche, source, limit),
        )


def update_parser_run(run_id: str, status: str, found_count: int, message: str, error: str = "", skipped_count: int = 0) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE parser_runs SET finished_at = ?, status = ?, found_count = ?, skipped_count = ?, message = ?, error = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), status, found_count, skipped_count, message, error, run_id),
        )


def list_parser_runs(limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM parser_runs ORDER BY started_at DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
    return [dict(row) for row in rows]


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


def _serialize(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "created_at": row["created_at"], "source": row["source"], "city": row["city"],
        "niche": row["niche"], "category": row["niche"], "name": row["name"], "address": row["address"],
        "phone": row["phone"], "website": row["website"], "rating": row["rating"], "reviews": row["reviews"],
        "card_url": row["card_url"], "social_url": row["social_url"], "contacts": _json_list(row["contacts_json"], []),
        "branch_count": row["branch_count"], "status": row["status"], "next_step": row["next_step"],
        "pain": row["pain"], "match_score": row["match_score"], "lead_score": row["lead_score"],
        "lead_score_max": LEAD_SCORE_MAX, "lead_score_reasons": _json_list(row["lead_score_reasons_json"], []),
        "tags": _json_list(row["tags_json"], []),
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
    with _connect() as connection:
        for incoming in leads:
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
            inserted_ids.append(int(cursor.lastrowid))

    return {
        "clients": list_clients(), "inserted_count": inserted_count,
        "duplicate_count": duplicate_count, "inserted_ids": inserted_ids,
    }


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
