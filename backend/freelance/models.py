from __future__ import annotations

from dataclasses import dataclass, field


FREELANCE_SOURCES = ("kwork", "fl", "freelance_ru", "workzilla", "freelancehunt", "profi", "youdo")
FREELANCE_STATUSES = ("Новый", "Написал", "Откликнулся", "Ответили", "Созвон", "В работе", "Завершён", "Отказ")


@dataclass(frozen=True)
class FreelanceOrder:
    source: str
    external_id: str
    title: str
    description: str = ""
    url: str = ""
    customer: str = ""
    categories: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    budget_min: int | None = None
    budget_max: int | None = None
    currency: str = "RUB"
    budget_text: str = ""
    published_at: str = ""
    discovered_at: str = ""
    relevance: int = 0
    relevance_reasons: tuple[str, ...] = ()
    status: str = "Новый"
    next_step: str = "Изучить заказ"
    note: str = ""
    archived: bool = False


@dataclass(frozen=True)
class FreelanceOrderFilters:
    query: str = ""
    source: str = ""
    status: str = ""
    category: str = ""
    min_budget: int | None = None
    sort: str = "relevance"
    include_archived: bool = False


@dataclass(frozen=True)
class FreelanceSettings:
    sources: tuple[str, ...] = FREELANCE_SOURCES
    keywords: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    min_budget: int = 0
    interval_seconds: int = 60
    sniper_enabled: bool = False
    telegram_enabled: bool = False


@dataclass(frozen=True)
class AdapterResult:
    source: str
    status: str
    orders: tuple[FreelanceOrder, ...] = ()
    checked_at: str = ""
    error: str = ""
    auth_required: bool = False


@dataclass(frozen=True)
class SourceStatus:
    source: str
    status: str
    checked_at: str = ""
    order_count: int = 0
    error: str = ""
    auth_required: bool = False
