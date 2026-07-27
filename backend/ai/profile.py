from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from ..database import _connect


@dataclass(frozen=True)
class ExecutorProfile:
    """Кто пишет письмо. Без этого модель выдаёт безликий текст «мы команда профессионалов»."""

    name: str = "Семён"
    role: str = "делаю сайты, онлайн-запись и автоматизацию для клиник и малого бизнеса"
    stack: str = "React, Next.js, Tilda, Telegram-боты, интеграции с CRM и amoCRM"
    portfolio_url: str = "https://semyon-lobanov-portfolio.vercel.app/"
    price_from: str = "от 35 000 ₽ за сайт с онлайн-записью"
    cases: str = "делал сайты с онлайн-записью для медицинских и сервисных компаний"
    # Маленький первый шаг: просить о покупке в первом сообщении — верный способ получить игнор.
    offer: str = "варианты по стоимости и срокам без обязательного созвона и длинной презентации"
    tone: str = "по-человечески, коротко, без канцелярита и без пафоса"
    signature: str = "Семён"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "stack": self.stack,
            "portfolio_url": self.portfolio_url,
            "price_from": self.price_from,
            "cases": self.cases,
            "offer": self.offer,
            "tone": self.tone,
            "signature": self.signature,
        }

    def as_prompt_block(self) -> str:
        return (
            f"Имя: {self.name}\n"
            f"Чем занимается: {self.role}\n"
            f"Стек и инструменты: {self.stack}\n"
            f"Портфолио: {self.portfolio_url}\n"
            f"Цены: {self.price_from}\n"
            f"Опыт: {self.cases}\n"
            f"Что предлагает первым шагом: {self.offer}\n"
            f"Тон общения: {self.tone}\n"
            f"Подпись: {self.signature}"
        )


FIELDS = tuple(ExecutorProfile().as_dict())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_profile_schema() -> None:
    columns = ",\n                ".join(f"{field} TEXT NOT NULL DEFAULT ''" for field in FIELDS)
    with _connect() as connection:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS ai_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                {columns},
                updated_at TEXT NOT NULL
            )
            """
        )


def get_profile() -> ExecutorProfile:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM ai_profile WHERE id = 1").fetchone()
    if row is None:
        return ExecutorProfile()
    stored = {field: (dict(row).get(field) or "") for field in FIELDS}
    # Пустые поля заменяем значениями по умолчанию: полупустой профиль хуже, чем дефолтный.
    defaults = ExecutorProfile()
    values = {key: value for key, value in stored.items() if value.strip()}
    if values.get("portfolio_url", "").rstrip("/") == "https://semyon-lobanov.vercel.app":
        values["portfolio_url"] = defaults.portfolio_url
    return replace(defaults, **values)


def save_profile(profile: ExecutorProfile) -> ExecutorProfile:
    values = profile.as_dict()
    assignments = ", ".join(f"{field} = excluded.{field}" for field in FIELDS)
    placeholders = ", ".join("?" for _ in FIELDS)
    with _connect() as connection:
        connection.execute(
            f"""
            INSERT INTO ai_profile (id, {', '.join(FIELDS)}, updated_at)
            VALUES (1, {placeholders}, ?)
            ON CONFLICT(id) DO UPDATE SET {assignments}, updated_at = excluded.updated_at
            """,
            (*[values[field] for field in FIELDS], _now()),
        )
    return get_profile()
