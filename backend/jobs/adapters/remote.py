from __future__ import annotations

import json
import re
import warnings
from html import unescape
from urllib.parse import urlencode

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# RSS разбирается html.parser'ом осознанно — предупреждение об этом не нужно в логах.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from ..models import JobSettings, JobVacancy
from .base import COMMON_SKILLS, HttpJobAdapter, clean_text, extract_tags, format_salary, is_developer_role, now_iso, source_url


# Вилки вида "$30k - $100k" или "$120,000 — $150,000".
USD_PATTERN = re.compile(r"\$\s*([\d][\d,.\s]*)\s*(k|тыс)?", re.IGNORECASE)


def parse_usd_range(value: str) -> tuple[int | None, int | None]:
    """Разбирает долларовую вилку, понимая сокращение k."""

    amounts: list[int] = []
    for raw, suffix in USD_PATTERN.findall(clean_text(value)):
        digits = raw.replace(",", "").replace(" ", "").rstrip(".")
        if not digits:
            continue
        try:
            amount = int(float(digits))
        except ValueError:
            continue
        if suffix:
            amount *= 1000
        amounts.append(amount)
    if not amounts:
        return None, None
    if len(amounts) == 1:
        return amounts[0], None
    return min(amounts[:2]), max(amounts[:2])


class RemoteOkAdapter(HttpJobAdapter):
    """RemoteOK: открытый JSON со сплошь удалёнными вакансиями и зарплатой в долларах."""

    source = "remoteok"
    url = "https://remoteok.com/api"

    def request_urls(self, settings: JobSettings) -> list[str]:
        base = source_url(self.source, self.url)
        tags = [keyword.strip().lower() for keyword in settings.keywords if keyword.strip()]
        # Один тег на запрос: RemoteOK не умеет объединять теги через OR.
        return [f"{base}?{urlencode({'tags': tag})}" for tag in tags[:4]] or [base]

    def parse(self, payload: str, settings: JobSettings) -> list[JobVacancy]:
        data = json.loads(payload)
        if not isinstance(data, list):
            return []
        vacancies: list[JobVacancy] = []
        for item in data:
            # Первый элемент выдачи — юридическая справка, а не вакансия.
            if not isinstance(item, dict) or not item.get("position"):
                continue
            external_id = clean_text(item.get("id"))
            role = clean_text(item.get("position"))
            if not external_id or not role:
                continue
            salary_min = item.get("salary_min") if isinstance(item.get("salary_min"), int) else None
            salary_max = item.get("salary_max") if isinstance(item.get("salary_max"), int) else None
            if salary_min == 0:
                salary_min = None
            if salary_max == 0:
                salary_max = None
            tags = [clean_text(tag) for tag in (item.get("tags") or []) if clean_text(tag)]
            description = BeautifulSoup(unescape(str(item.get("description") or "")), "html.parser").get_text(" ", strip=True)
            if not is_developer_role(role):
                continue
            vacancies.append(JobVacancy(
                source=self.source,
                external_id=f"remoteok-{external_id}",
                company=clean_text(item.get("company")) or "Без названия",
                role=role,
                description=description[:1500],
                url=clean_text(item.get("url")) or clean_text(item.get("apply_url")),
                tags=tuple(dict.fromkeys(tags))[:8],
                salary_min=salary_min,
                salary_max=salary_max,
                currency="USD",
                salary_text=format_salary(salary_min, salary_max, "USD"),
                location=clean_text(item.get("location")) or "Remote",
                employment="Удалённо · оплата в валюте",
                published_at=clean_text(item.get("date")),
                discovered_at=now_iso(),
            ))
        return vacancies


class RemotiveAdapter(HttpJobAdapter):
    """Remotive: агрегатор удалённых вакансий с понятной JSON-выдачей."""

    source = "remotive"
    url = "https://remotive.com/api/remote-jobs"

    def request_urls(self, settings: JobSettings) -> list[str]:
        base = source_url(self.source, self.url)
        query = " ".join(keyword.strip() for keyword in settings.keywords if keyword.strip())
        params = {"limit": str(max(10, min(settings.per_source_limit, 100)))}
        if query:
            params["search"] = query
        return [f"{base}?{urlencode(params)}"]

    def parse(self, payload: str, settings: JobSettings) -> list[JobVacancy]:
        data = json.loads(payload)
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, list):
            return []
        vacancies: list[JobVacancy] = []
        for item in jobs:
            if not isinstance(item, dict):
                continue
            external_id = clean_text(item.get("id"))
            role = clean_text(item.get("title"))
            if not external_id or not role:
                continue
            salary_min, salary_max = parse_usd_range(str(item.get("salary") or ""))
            description = BeautifulSoup(unescape(str(item.get("description") or "")), "html.parser").get_text(" ", strip=True)
            tags = [clean_text(tag) for tag in (item.get("tags") or []) if clean_text(tag)]
            if not is_developer_role(role):
                continue
            vacancies.append(JobVacancy(
                source=self.source,
                external_id=f"remotive-{external_id}",
                company=clean_text(item.get("company_name")) or "Без названия",
                role=role,
                description=description[:1500],
                url=clean_text(item.get("url")),
                tags=tuple(dict.fromkeys(tags or extract_tags(f"{role} {description}", COMMON_SKILLS)))[:8],
                salary_min=salary_min,
                salary_max=salary_max,
                currency="USD",
                salary_text=clean_text(item.get("salary")) or format_salary(salary_min, salary_max, "USD"),
                location=clean_text(item.get("candidate_required_location")) or "Remote",
                employment=f"Удалённо · {clean_text(item.get('job_type')) or 'full time'}",
                published_at=clean_text(item.get("publication_date")),
                discovered_at=now_iso(),
            ))
        return vacancies


class WeWorkRemotelyAdapter(HttpJobAdapter):
    """We Work Remotely: RSS с прямыми вакансиями компаний, без посредников."""

    source = "weworkremotely"
    url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"

    def request_urls(self, settings: JobSettings) -> list[str]:
        feeds = [source_url(self.source, self.url)]
        if not settings.remote_only:
            feeds.append("https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss")
        return feeds

    def parse(self, payload: str, settings: JobSettings) -> list[JobVacancy]:
        # html.parser, а не xml: сборщик lxml в зависимости проекта не входит,
        # а RSS этот разбирает без него. Гасим предупреждение точечно, потому что
        # глобальный фильтр сбрасывается запуском тестов.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(payload, "html.parser")
        vacancies: list[JobVacancy] = []
        for item in soup.find_all("item"):
            # guid, а не link: html.parser считает <link> пустым тегом и текст теряется.
            guid = item.find("guid")
            link = clean_text(guid.get_text() if guid else "")
            raw_title = clean_text(item.find("title").get_text() if item.find("title") else "")
            if not link or not raw_title:
                continue
            # Заголовок приходит в виде "Компания: Должность".
            company, _, role = raw_title.partition(":")
            role = clean_text(role) or raw_title
            description_node = item.find("description")
            description = BeautifulSoup(
                unescape(description_node.get_text() if description_node else ""), "html.parser"
            ).get_text(" ", strip=True)
            region = item.find("region")
            category = item.find("category")
            external_id = link.rstrip("/").rsplit("/", 1)[-1]
            if not is_developer_role(role):
                continue
            # Зарплату из описания не достаём: там попадаются часовые ставки и
            # случайные суммы, и «от 11 $» выглядело бы как вилка вакансии.
            salary_min, salary_max = None, None
            vacancies.append(JobVacancy(
                source=self.source,
                external_id=f"wwr-{external_id}",
                company=clean_text(company) or "Без названия",
                role=role,
                description=description[:1500],
                url=link,
                tags=extract_tags(f"{role} {description}", COMMON_SKILLS),
                salary_min=salary_min,
                salary_max=salary_max,
                currency="USD",
                salary_text=format_salary(salary_min, salary_max, "USD"),
                location=clean_text(region.get_text()) if region else "Anywhere in the World",
                employment=f"Удалённо · {clean_text(category.get_text()) if category else 'programming'}",
                published_at=clean_text(item.find("pubDate").get_text() if item.find("pubDate") else ""),
                discovered_at=now_iso(),
            ))
        return vacancies
