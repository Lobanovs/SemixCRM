from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urljoin

import httpx

from ..models import AdapterResult, FreelanceOrder, FreelanceSettings


USER_AGENT = "SemixCRM/1.0 (+local freelance monitor)"


class SourceAdapter(Protocol):
    source: str
    requires_browser: bool

    def collect(self, settings: FreelanceSettings) -> AdapterResult:
        ...


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_amount(value: str) -> int | None:
    cleaned = value.replace("\u00a0", " ").replace("₽", " ").replace("руб.", " ")
    values = [int(item.replace(" ", "")) for item in re.findall(r"\d[\d\s]{2,}", cleaned)]
    return min(values) if values else None


def order_from_card(source: str, title: str, href: str, description: str = "", budget_text: str = "", category: str = "", external_id: str = "") -> FreelanceOrder:
    resolved_url = href.strip()
    inferred_id = external_id.strip() or (re.findall(r"(?:project|projects|task|tasks)[/-]([\w-]+)", resolved_url) or [resolved_url])[0]
    budget_min = parse_amount(budget_text)
    return FreelanceOrder(
        source=source,
        external_id=inferred_id,
        title=" ".join(title.split()),
        description=" ".join(description.split()),
        url=resolved_url,
        categories=(category.strip(),) if category.strip() else (),
        budget_min=budget_min,
        budget_text=" ".join(budget_text.split()),
        published_at="",
        discovered_at=now_iso(),
    )


class PublicHttpAdapter:
    source = ""
    requires_browser = False
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

    def fetch(self) -> str:
        with self.client_factory(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20) as client:
            response = client.get(self.url)
            response.raise_for_status()
            return response.text

    def parse_html(self, html: str) -> list[FreelanceOrder]:
        raise NotImplementedError

    def collect(self, settings: FreelanceSettings) -> AdapterResult:
        for attempt in range(self.max_attempts):
            try:
                orders = self.parse_html(self.fetch())
                return AdapterResult(self.source, "done" if orders else "empty", tuple(orders), now_iso())
            except httpx.HTTPStatusError as error:
                return AdapterResult(self.source, "error", checked_at=now_iso(), error=f"HTTP {error.response.status_code}")
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt + 1 < self.max_attempts:
                    self.sleeper(self.retry_delay)
                    continue
                return AdapterResult(self.source, "error", checked_at=now_iso(), error=f"Сетевая ошибка: {error}")
            except httpx.HTTPError as error:
                return AdapterResult(self.source, "error", checked_at=now_iso(), error=f"Сетевая ошибка: {error}")
            except Exception as error:  # noqa: BLE001 - surface source-specific parser failures
                return AdapterResult(self.source, "error", checked_at=now_iso(), error=f"Ошибка разбора: {error}")
        return AdapterResult(self.source, "error", checked_at=now_iso(), error="Источник не ответил")


def source_url(source: str, default: str) -> str:
    return os.getenv(f"FREELANCE_{source.upper()}_URL", default)


def absolute_url(base: str, href: str) -> str:
    return urljoin(base, href.strip())
