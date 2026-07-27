from __future__ import annotations

from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from ..models import JobSettings, JobVacancy
from .base import HttpJobAdapter, clean_text, format_salary, now_iso, parse_salary_range, source_url


BASE_URL = "https://career.habr.com"
LIST_URL = f"{BASE_URL}/vacancies"


class HabrAdapter(HttpJobAdapter):
    """Хабр Карьера: обычная HTML-выдача поиска вакансий."""

    source = "habr"

    def request_urls(self, settings: JobSettings) -> list[str]:
        query = " ".join(keyword for keyword in settings.keywords if keyword.strip())
        params = {"q": query or "разработчик", "type": "all"}
        if settings.remote_only:
            params["remote"] = "true"
        if settings.salary_min:
            params["salary"] = str(settings.salary_min)
        return [f"{source_url(self.source, LIST_URL)}?{urlencode(params)}"]

    def parse(self, payload: str, settings: JobSettings) -> list[JobVacancy]:
        soup = BeautifulSoup(payload, "html.parser")
        vacancies: list[JobVacancy] = []
        for card in soup.select(".vacancy-card"):
            link = card.select_one(".vacancy-card__title-link[href]")
            if link is None:
                continue
            role = clean_text(link.get_text(" ", strip=True))
            href = str(link.get("href") or "")
            external_id = href.rstrip("/").rsplit("/", 1)[-1]
            if not role or not external_id:
                continue

            company_node = card.select_one(".vacancy-card__company a")
            date_node = card.select_one(".vacancy-card__date time")
            salary_node = card.select_one(".vacancy-card__salary")
            skills = [clean_text(chip.get_text()) for chip in card.select(".vacancy-card__skills-chip")]

            salary_min, salary_max, salary_text = self._read_salary(salary_node)

            vacancies.append(JobVacancy(
                source=self.source,
                external_id=f"habr-{external_id}",
                company=clean_text(company_node.get_text()) if company_node else "Без названия",
                role=role,
                description=", ".join(skills),
                url=urljoin(BASE_URL, href),
                tags=tuple(dict.fromkeys(skills))[:8],
                salary_min=salary_min,
                salary_max=salary_max,
                salary_text=salary_text,
                location=clean_text(card.select_one(".vacancy-card__meta").get_text(" ", strip=True)) if card.select_one(".vacancy-card__meta") else "",
                published_at=clean_text(date_node.get("datetime")) if date_node else "",
                discovered_at=now_iso(),
            ))
        return vacancies

    @staticmethod
    def _read_salary(node: object) -> tuple[int | None, int | None, str]:
        """Хабр показывает либо реальную вилку, либо прогноз «похожие специалисты получают»."""

        if node is None:
            return None, None, ""
        text = clean_text(node.get_text(" ", strip=True))  # type: ignore[union-attr]
        if not text:
            return None, None, ""
        if "не указана" in text.lower():
            predicted_min, predicted_max = parse_salary_range(text)
            hint = format_salary(predicted_min, predicted_max)
            # Прогноз Хабра не является обещанием работодателя — в числовые поля он не идёт.
            return None, None, f"≈ {hint}" if hint else ""
        salary_min, salary_max = parse_salary_range(text)
        return salary_min, salary_max, text
