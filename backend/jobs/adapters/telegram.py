from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import JobSettings, JobVacancy
from .base import COMMON_SKILLS, HttpJobAdapter, clean_text, extract_tags, format_salary, now_iso, parse_salary_range


PREVIEW_URL = "https://t.me/s/{channel}"

# Признаки того, что пост в канале — вакансия, а не объявление или дайджест.
VACANCY_MARKERS = (
    "вакансия", "ищем", "требуется", "ищу разработчика", "в команду", "зарплата",
    "оклад", "удалённо", "удаленно", "remote", "full-time", "part-time", "опыт от",
    "we are looking", "hiring", "офис", "гибрид", "з/п", "вилка",
)
COMPANY_PATTERN = re.compile(r"(?:\s+в\s+|\s+—\s+|\s+-\s+|\s+@\s*)([A-ZА-ЯЁ][\w .&'’\-]{1,40})")
SALARY_LINE_PATTERN = re.compile(r"[^\n]*(?:₽|руб|\$|€|з/п|зарплата|вилка)[^\n]*", re.IGNORECASE)


class TelegramAdapter(HttpJobAdapter):
    """Публичные каналы с вакансиями — читаются через веб-превью t.me/s/<канал>."""

    source = "telegram"

    def request_urls(self, settings: JobSettings) -> list[str]:
        channels = [channel.strip().lstrip("@").strip("/") for channel in settings.telegram_channels]
        return [PREVIEW_URL.format(channel=channel) for channel in channels if channel]

    def parse(self, payload: str, settings: JobSettings) -> list[JobVacancy]:
        soup = BeautifulSoup(payload, "html.parser")
        vacancies: list[JobVacancy] = []
        for message in soup.select(".tgme_widget_message[data-post]"):
            post = str(message.get("data-post") or "")
            text_node = message.select_one(".tgme_widget_message_text")
            if not post or text_node is None:
                continue
            channel, _, post_id = post.partition("/")
            body = text_node.get_text("\n", strip=True)
            if not self._looks_like_vacancy(body, settings):
                continue

            role, company = self._split_headline(self._headline(body), channel)
            salary_source = SALARY_LINE_PATTERN.search(body)
            salary_min, salary_max = parse_salary_range(salary_source.group(0)) if salary_source else (None, None)
            time_node = message.select_one("time[datetime]")

            vacancies.append(JobVacancy(
                source=self.source,
                external_id=f"tg-{channel}-{post_id}",
                company=company,
                role=role[:200],
                description=clean_text(body)[:1500],
                url=f"https://t.me/{post}",
                tags=extract_tags(body, COMMON_SKILLS),
                salary_min=salary_min,
                salary_max=salary_max,
                salary_text=format_salary(salary_min, salary_max) if (salary_min or salary_max) else "",
                location="Удалённо" if self._is_remote(body) else "",
                employment=f"Telegram · @{channel}",
                published_at=clean_text(time_node.get("datetime")) if time_node else "",
                discovered_at=now_iso(),
            ))
        return vacancies

    @staticmethod
    def _looks_like_vacancy(body: str, settings: JobSettings) -> bool:
        if len(body) < 60:
            return False
        lowered = body.lower()
        if any(marker in lowered for marker in VACANCY_MARKERS):
            return True
        return any(keyword.strip().lower() in lowered for keyword in settings.keywords if keyword.strip())

    @staticmethod
    def _is_remote(body: str) -> bool:
        lowered = body.lower()
        return any(marker in lowered for marker in ("удалённ", "удаленн", "remote"))

    @staticmethod
    def _headline(body: str) -> str:
        """Первая содержательная строка поста: декоративные эмодзи заголовком не считаются."""

        for line in body.split("\n"):
            cleaned = clean_text(line)
            if len(re.findall(r"[\w]", cleaned)) >= 8:
                return cleaned
        return clean_text(next((line for line in body.split("\n") if line.strip()), ""))

    @staticmethod
    def _split_headline(headline: str, channel: str) -> tuple[str, str]:
        cleaned = clean_text(headline)
        match = COMPANY_PATTERN.search(cleaned)
        if match is None:
            return cleaned or f"Вакансия из @{channel}", f"@{channel}"
        company = clean_text(match.group(1)).rstrip(".,;:")
        role = clean_text(cleaned[: match.start()]) or cleaned
        return role, company or f"@{channel}"
