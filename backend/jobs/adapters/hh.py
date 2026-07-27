from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from ..models import JobSettings, JobVacancy
from .base import COMMON_SKILLS, HttpJobAdapter, clean_text, extract_tags, format_salary, now_iso, source_url


HIGHLIGHT_PATTERN = re.compile(r"</?highlighttext>")

# Официальный публичный API hh.ru: ключи не нужны, только User-Agent.
API_URL = "https://api.hh.ru/vacancies"


class HhAdapter(HttpJobAdapter):
    source = "hh"

    def request_urls(self, settings: JobSettings) -> list[str]:
        text = " OR ".join(keyword for keyword in settings.keywords if keyword.strip())
        params: dict[str, str] = {
            "text": text or "разработчик",
            "area": settings.hh_area(),
            "per_page": str(max(1, min(settings.per_source_limit, 100))),
            "page": "0",
            "order_by": "publication_time",
        }
        if settings.salary_min:
            params["salary"] = str(settings.salary_min)
            params["only_with_salary"] = "true"
        if settings.remote_only:
            params["schedule"] = "remote"
        return [f"{source_url(self.source, API_URL)}?{urlencode(params)}"]

    def parse(self, payload: str, settings: JobSettings) -> list[JobVacancy]:
        data = json.loads(payload)
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        vacancies: list[JobVacancy] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            external_id = clean_text(item.get("id"))
            role = clean_text(item.get("name"))
            if not external_id or not role:
                continue
            employer = item.get("employer") if isinstance(item.get("employer"), dict) else {}
            salary = item.get("salary") if isinstance(item.get("salary"), dict) else {}
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            area = item.get("area") if isinstance(item.get("area"), dict) else {}
            schedule = item.get("schedule") if isinstance(item.get("schedule"), dict) else {}

            description = HIGHLIGHT_PATTERN.sub(
                "", f"{clean_text(snippet.get('responsibility'))} {clean_text(snippet.get('requirement'))}"
            ).strip()
            salary_min = salary.get("from") if isinstance(salary.get("from"), int) else None
            salary_max = salary.get("to") if isinstance(salary.get("to"), int) else None
            currency = clean_text(salary.get("currency")) or "RUR"

            vacancies.append(JobVacancy(
                source=self.source,
                external_id=f"hh-{external_id}",
                company=clean_text(employer.get("name")) or "Без названия",
                role=role,
                description=description,
                url=clean_text(item.get("alternate_url")) or f"https://hh.ru/vacancy/{external_id}",
                tags=extract_tags(f"{role} {description}", COMMON_SKILLS),
                salary_min=salary_min,
                salary_max=salary_max,
                currency=currency,
                salary_text=format_salary(salary_min, salary_max, currency),
                location=clean_text(area.get("name")),
                employment=clean_text(schedule.get("name")),
                published_at=clean_text(item.get("published_at")),
                discovered_at=now_iso(),
            ))
        return vacancies
