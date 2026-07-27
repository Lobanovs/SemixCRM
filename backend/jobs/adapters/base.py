from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Callable

import httpx

from ..models import JobAdapterResult, JobSettings, JobVacancy


USER_AGENT = "SemixCRM/1.0 (+local job monitor)"
TAG_PATTERN = re.compile(r"[A-Za-zА-Яа-я0-9+#.\-]{2,}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def source_url(source: str, default: str) -> str:
    return os.getenv(f"JOBS_{source.upper()}_URL", default)


def format_salary(salary_min: int | None, salary_max: int | None, currency: str = "RUB") -> str:
    symbol = {"RUR": "₽", "RUB": "₽", "USD": "$", "EUR": "€"}.get(currency.upper(), currency)

    def spaced(amount: int) -> str:
        return f"{amount:,}".replace(",", " ")

    if salary_min and salary_max:
        return f"{spaced(salary_min)} – {spaced(salary_max)} {symbol}"
    if salary_min:
        return f"от {spaced(salary_min)} {symbol}"
    if salary_max:
        return f"до {spaced(salary_max)} {symbol}"
    return ""


AMOUNT_PATTERN = re.compile(r"\d[\d\s ]{2,}")


def parse_salary_range(text: str) -> tuple[int | None, int | None]:
    """Достаёт вилку из свободного текста: «от 200 000 ₽», «150 000 – 245 000 ₽», «до 300 000»."""

    cleaned = clean_text(text).replace(" ", " ")
    amounts = [int(match.group(0).replace(" ", "")) for match in AMOUNT_PATTERN.finditer(cleaned)]
    amounts = [amount for amount in amounts if amount >= 1000]
    if not amounts:
        return None, None
    lowered = cleaned.lower()
    if len(amounts) >= 2:
        return min(amounts[:2]), max(amounts[:2])
    if lowered.startswith("до") or " до " in lowered.split("от")[-1][:6]:
        return None, amounts[0]
    return amounts[0], None


def extract_tags(text: str, known: tuple[str, ...]) -> tuple[str, ...]:
    """Вытаскивает знакомые технологии из свободного текста вакансии."""

    lowered = text.lower()
    found = [item for item in known if item.lower() in lowered]
    return tuple(dict.fromkeys(found))[:8]


# Признаки того, что вакансия про разработку. Агрегаторы удалёнки отдают вперемешку
# продажи, поддержку и ввод данных — без отбора база забивается мусором.
DEV_ROLE_MARKERS = (
    "developer", "engineer", "programmer", "разработчик", "программист", "инженер",
    "frontend", "front-end", "front end", "backend", "back-end", "back end", "fullstack",
    "full-stack", "full stack", "software", "web dev", "webdev", "devops", "sre",
    "react", "vue", "angular", "svelte", "next.js", "node", "python", "django", "fastapi",
    "php", "laravel", "java", "kotlin", "golang", " go ", "ruby", "rails", "swift", "flutter",
    "typescript", "javascript", "wordpress", "bitrix", "битрикс", "tilda", "тильда",
    "верстальщик", "вёрстка", "верстка", "автоматизац", "интеграц", "боты", "бот",
    "qa ", "тестировщик", "data engineer", "ml engineer", "mobile", "ios", "android",
    "техлид", "tech lead", "cto", "архитектор",
)

# Роли, которые часто содержат технические слова, но разработкой не являются.
NON_DEV_ROLES = (
    "business development", "sales", "account executive", "recruiter", "data entry",
    "customer support", "content reviewer", "moderator", "copywriter", "marketing manager",
    "продаж", "менеджер по работе", "оператор", "модератор", "рекрутер", "ассистент",
)


def is_developer_role(role: str, fallback: str = "") -> bool:
    """Похожа ли вакансия на разработку.

    Решает название должности. Теги агрегаторов для этого не годятся: RemoteOK
    вешает на каждую вакансию десятки тегов, включая react и python, из-за чего
    «Concept Artist» проходил как разработка. Fallback передают только источники
    с ненадёжным заголовком — например посты из Telegram.
    """

    title = clean_text(role).lower().replace("ё", "е")
    if any(marker in title for marker in NON_DEV_ROLES):
        return False
    if any(marker in title for marker in DEV_ROLE_MARKERS):
        return True
    if not fallback:
        return False
    text = clean_text(fallback).lower().replace("ё", "е")[:400]
    return any(marker in text for marker in DEV_ROLE_MARKERS)


COMMON_SKILLS = (
    "React", "Vue", "Angular", "Svelte", "Next.js", "Nuxt", "TypeScript", "JavaScript",
    "Node.js", "Python", "Django", "FastAPI", "Go", "PHP", "Laravel", "Ruby", "Java",
    "Kotlin", "Swift", "Flutter", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Docker",
    "Kubernetes", "GraphQL", "REST", "Redux", "Tailwind", "CSS", "HTML", "WordPress",
    "Tilda", "Bitrix", "1C", "SQL", "Git", "Linux", "AWS", "Figma",
)


class HttpJobAdapter:
    """Базовый источник вакансий, который забирается обычным HTTP-запросом."""

    source = ""
    url = ""

    def __init__(
        self,
        client_factory: Callable[..., httpx.Client] | None = None,
        *,
        max_attempts: int = 2,
        retry_delay: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client_factory = client_factory or (lambda **kwargs: httpx.Client(**kwargs))
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay = max(0.0, float(retry_delay))
        self.sleeper = sleeper

    def request_urls(self, settings: JobSettings) -> list[str]:
        raise NotImplementedError

    def fetch(self, url: str) -> str:
        with self.client_factory(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    def parse(self, payload: str, settings: JobSettings) -> list[JobVacancy]:
        raise NotImplementedError

    def _fetch_with_retry(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return self.fetch(url)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = error
                if attempt + 1 < self.max_attempts:
                    self.sleeper(self.retry_delay)
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("Источник не ответил")

    def collect(self, settings: JobSettings) -> JobAdapterResult:
        urls = self.request_urls(settings)
        if not urls:
            return JobAdapterResult(self.source, "empty", checked_at=now_iso())
        vacancies: list[JobVacancy] = []
        errors: list[str] = []
        for url in urls:
            try:
                vacancies.extend(self.parse(self._fetch_with_retry(url), settings))
            except httpx.HTTPStatusError as error:
                errors.append(f"HTTP {error.response.status_code}")
            except httpx.HTTPError as error:
                errors.append(f"Сетевая ошибка: {error}")
            except Exception as error:  # noqa: BLE001 - показываем сбой конкретного источника
                errors.append(f"Ошибка разбора: {error}")
        if vacancies:
            return JobAdapterResult(self.source, "done", tuple(vacancies), now_iso())
        if errors:
            return JobAdapterResult(self.source, "error", checked_at=now_iso(), error="; ".join(dict.fromkeys(errors))[:400])
        return JobAdapterResult(self.source, "empty", checked_at=now_iso())
