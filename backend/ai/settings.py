from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..database import _connect


DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_TIMEOUT = 90.0
MIN_TIMEOUT = 5.0
MAX_TIMEOUT = 300.0

# Только модели с официальным OpenAI-совместимым /chat/completions.
# Модели OpenCode Go с Anthropic-style /messages здесь намеренно не показываем.
SUPPORTED_MODELS: tuple[tuple[str, str], ...] = (
    ("gpt-5.6-luna", "GPT-5.6 Luna"),
    ("deepseek-v4-flash", "DeepSeek V4 Flash"),
    ("deepseek-v4-pro", "DeepSeek V4 Pro"),
    ("glm-5.2", "GLM-5.2"),
    ("glm-5.1", "GLM-5.1"),
    ("kimi-k3", "Kimi K3"),
    ("kimi-k2.7-code", "Kimi K2.7 Code"),
    ("kimi-k2.6", "Kimi K2.6"),
    ("mimo-v2.5", "MiMo-V2.5"),
    ("mimo-v2.5-pro", "MiMo-V2.5 Pro"),
    ("grok-4.5", "Grok 4.5"),
    ("hy3", "Hy3"),
)
SUPPORTED_MODEL_IDS = frozenset(model_id for model_id, _ in SUPPORTED_MODELS)


@dataclass(frozen=True)
class StoredSettings:
    # None означает «использовать окружение», пустая строка — «явно выключено».
    api_key: str | None
    model: str
    timeout: float
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validated_model(model: str) -> str:
    value = model.strip()
    if value not in SUPPORTED_MODEL_IDS:
        raise ValueError("Выберите поддерживаемую модель OpenCode Go")
    return value


def _validated_timeout(timeout: float | int) -> float:
    value = float(timeout)
    if not MIN_TIMEOUT <= value <= MAX_TIMEOUT:
        raise ValueError(f"Таймаут должен быть от {int(MIN_TIMEOUT)} до {int(MAX_TIMEOUT)} секунд")
    return value


def validate_settings_values(model: str, timeout: float | int) -> tuple[str, float]:
    return _validated_model(model), _validated_timeout(timeout)


def _environment_timeout() -> float:
    try:
        return _validated_timeout(float(os.getenv("OPENCODE_TIMEOUT", DEFAULT_TIMEOUT)))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


def init_settings_schema() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                api_key TEXT,
                model TEXT NOT NULL,
                timeout REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def read_stored_settings() -> StoredSettings | None:
    init_settings_schema()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM ai_settings WHERE id = 1").fetchone()
    if row is None:
        return None
    return StoredSettings(
        api_key=row["api_key"],
        model=row["model"],
        timeout=float(row["timeout"]),
        updated_at=row["updated_at"],
    )


def resolved_settings() -> dict[str, Any]:
    stored = read_stored_settings()
    environment_key = os.getenv("OPENCODE_API_KEY", "").strip()
    environment_model = os.getenv("OPENCODE_MODEL", DEFAULT_MODEL).strip()
    if environment_model not in SUPPORTED_MODEL_IDS:
        environment_model = DEFAULT_MODEL

    if stored is None:
        key = environment_key
        return {
            "api_key": key,
            "api_key_source": "environment" if key else "",
            "model": environment_model,
            "base_url": DEFAULT_BASE_URL,
            "timeout": _environment_timeout(),
            "updated_at": "",
        }

    if stored.api_key is None:
        key = environment_key
        source = "environment" if key else ""
    else:
        key = stored.api_key
        source = "database" if key else ""
    return {
        "api_key": key,
        "api_key_source": source,
        "model": stored.model,
        "base_url": DEFAULT_BASE_URL,
        "timeout": stored.timeout,
        "updated_at": stored.updated_at,
    }


def _mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    tail = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"••••{tail}"


def safe_settings() -> dict[str, Any]:
    effective = resolved_settings()
    key = str(effective["api_key"])
    return {
        "enabled": bool(key),
        "api_key_configured": bool(key),
        "api_key_hint": _mask_key(key),
        "api_key_source": effective["api_key_source"],
        "model": effective["model"],
        "base_url": effective["base_url"],
        "timeout": effective["timeout"],
        "updated_at": effective["updated_at"],
        "supported_models": [
            {"id": model_id, "label": label}
            for model_id, label in SUPPORTED_MODELS
        ],
    }


def save_settings(*, api_key: str | None, model: str, timeout: float | int) -> dict[str, Any]:
    init_settings_schema()
    normalized_model, normalized_timeout = validate_settings_values(model, timeout)
    current = read_stored_settings()
    if api_key is None:
        stored_key = current.api_key if current is not None else None
    else:
        stored_key = api_key.strip()
        if not stored_key:
            raise ValueError("API-ключ не может быть пустым; для удаления используйте отдельную кнопку")
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO ai_settings (id, api_key, model, timeout, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                api_key = excluded.api_key,
                model = excluded.model,
                timeout = excluded.timeout,
                updated_at = excluded.updated_at
            """,
            (stored_key, normalized_model, normalized_timeout, _now()),
        )
    return safe_settings()


def remove_saved_key() -> bool:
    init_settings_schema()
    before = resolved_settings()
    current = read_stored_settings()
    model = current.model if current is not None else str(before["model"])
    timeout = current.timeout if current is not None else float(before["timeout"])
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO ai_settings (id, api_key, model, timeout, updated_at)
            VALUES (1, '', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                api_key = '',
                updated_at = excluded.updated_at
            """,
            (model, timeout, _now()),
        )
    return bool(before["api_key"])
