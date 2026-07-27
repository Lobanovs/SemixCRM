from __future__ import annotations

from dataclasses import dataclass, field


FREELANCE_SOURCES = ("kwork", "fl", "freelance_ru", "profi", "youdo")
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
    relevance_points: int = 0
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
class FreelanceCleanupRules:
    """Правила массовой уборки списка заказов.

    Пустое правило ничего не скрывает: чтобы убрать всё подряд, нужно явно
    выставить `include_everything`. Так случайный клик не уносит весь список.
    """

    max_relevance: int | None = None
    older_than_days: int | None = None
    sources: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    keep_worked: bool = True
    include_everything: bool = False

    def is_empty(self) -> bool:
        return not (
            self.include_everything
            or self.max_relevance is not None
            or self.older_than_days is not None
            or self.sources
            or self.statuses
        )


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
