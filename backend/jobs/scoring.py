from __future__ import annotations

from .models import JobSettings, JobVacancy


JOB_SCORE_MAX = 20


def _normalize(value: str) -> str:
    """Площадки пишут «Стажер» и «Стажёр» вперемешку — сравниваем без «ё»."""

    return value.lower().replace("ё", "е")


def score_vacancy(vacancy: JobVacancy, settings: JobSettings) -> tuple[int, list[str], int]:
    """Объяснимая релевантность: очки, причины и процент соответствия."""

    haystack = _normalize(f"{vacancy.role} {vacancy.description} {' '.join(vacancy.tags)}")
    role = _normalize(vacancy.role)
    reasons: list[str] = []
    score = 0

    excluded = [(word.strip(), _normalize(word.strip())) for word in settings.excluded_keywords if word.strip()]
    hit_excluded = next((original for original, normalized in excluded if normalized in haystack), "")
    if hit_excluded:
        return 0, [f"Стоп-слово «{hit_excluded}»"], 0

    keywords = [_normalize(word.strip()) for word in settings.keywords if word.strip()]
    title_hits = [word for word in keywords if word in role]
    body_hits = [word for word in keywords if word in haystack and word not in title_hits]
    if title_hits:
        score += min(len(title_hits) * 3, 9)
        reasons.append(f"В названии: {', '.join(title_hits[:3])}")
    if body_hits:
        score += min(len(body_hits), 4)
        reasons.append(f"В описании: {', '.join(body_hits[:3])}")

    if vacancy.salary_min or vacancy.salary_max:
        score += 2
        reasons.append("Указана зарплата")
    if vacancy.currency.upper() not in {"RUB", "RUR", ""}:
        # Валютная удалёнка ценна сама по себе, а рублёвый порог к ней неприменим.
        score += 3
        reasons.append(f"Оплата в валюте ({vacancy.currency.upper()})")
    elif settings.salary_min and (vacancy.salary_min or 0) >= settings.salary_min:
        score += 3
        reasons.append(f"Вилка от {settings.salary_min:,} ₽".replace(",", " "))
    if settings.remote_only and "удал" in f"{vacancy.location} {vacancy.employment}".lower():
        score += 2
        reasons.append("Удалённый формат")

    score = min(score, JOB_SCORE_MAX)
    if not reasons:
        reasons.append("Нет совпадений с ключевыми словами")
    return score, reasons, round(score / JOB_SCORE_MAX * 100)
