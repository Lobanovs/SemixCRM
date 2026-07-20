from __future__ import annotations

import re

from .models import FreelanceOrder, FreelanceSettings


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def score_order(order: FreelanceOrder, settings: FreelanceSettings) -> tuple[int, list[str]]:
    title = _normalize(order.title)
    body = _normalize(" ".join((order.description, *order.categories, *order.tags)))
    excluded = [word for word in settings.excluded_keywords if _normalize(word) and _normalize(word) in f"{title} {body}"]
    if excluded:
        return 0, [f"Исключающее слово: {excluded[0]}"]

    score = 0
    reasons: list[str] = []
    title_matches = [word for word in settings.keywords if _normalize(word) and _normalize(word) in title]
    body_matches = [word for word in settings.keywords if _normalize(word) and _normalize(word) in body and _normalize(word) not in title_matches]
    if title_matches:
        score += min(60, len(title_matches) * 30)
        reasons.append(f"Совпадение ключевого слова в названии: {', '.join(title_matches[:3])}")
    if body_matches:
        score += min(20, len(body_matches) * 10)
        reasons.append(f"Совпадение в описании или категории: {', '.join(body_matches[:3])}")
    budget_value = order.budget_max if order.budget_max is not None else order.budget_min
    if settings.min_budget and budget_value is not None and budget_value >= settings.min_budget:
        score += 15
        reasons.append("Бюджет соответствует минимуму")
    return min(100, score), reasons or ["Подходит по базовым фильтрам"]
