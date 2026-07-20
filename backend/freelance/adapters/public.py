from __future__ import annotations

import json
import re
from typing import Any, Callable

from bs4 import BeautifulSoup
import httpx

from ..models import AdapterResult, FreelanceOrder, FreelanceSettings
from .base import PublicHttpAdapter, absolute_url, now_iso, order_from_card, source_url


class FlAdapter(PublicHttpAdapter):
    source = "fl"
    url = source_url("fl", "https://www.fl.ru/projects/")

    def parse_html(self, html: str) -> list[FreelanceOrder]:
        soup = BeautifulSoup(html, "html.parser")
        orders: list[FreelanceOrder] = []
        for card in soup.select("article.project-card, .b-post, .project-card"):
            link = card.select_one("a.project-card__title, a.b-post__link, a[href*='/projects/']")
            if link is None or not link.get_text(" ", strip=True):
                continue
            href = absolute_url(self.url, str(link.get("href") or ""))
            orders.append(order_from_card(
                self.source,
                link.get_text(" ", strip=True),
                href,
                card.select_one(".project-card__description, .b-post__txt") .get_text(" ", strip=True) if card.select_one(".project-card__description, .b-post__txt") else "",
                card.select_one(".project-card__budget, .b-post__price").get_text(" ", strip=True) if card.select_one(".project-card__budget, .b-post__price") else "",
                card.select_one(".project-card__category, .b-post__tags").get_text(" ", strip=True) if card.select_one(".project-card__category, .b-post__tags") else "",
                f"{self.source}-{card.get('data-project-id')}" if card.get("data-project-id") else "",
            ))
        return orders


class KworkAdapter(FlAdapter):
    source = "kwork"
    url = source_url("kwork", "https://kwork.ru/projects")


class FreelanceRuAdapter(FlAdapter):
    source = "freelance_ru"
    url = source_url("freelance_ru", "https://freelance.ru/project/search")


class FreelancehuntAdapter(PublicHttpAdapter):
    source = "freelancehunt"
    url = source_url("freelancehunt", "https://api.freelancehunt.com/v2/projects")

    def fetch_json(self) -> dict[str, Any]:
        with self.client_factory(headers={"User-Agent": "SemixCRM/1.0", "Accept": "application/json"}, follow_redirects=True, timeout=20) as client:
            response = client.get(self.url)
            response.raise_for_status()
            return response.json()

    def collect(self, settings: FreelanceSettings) -> AdapterResult:
        try:
            payload = self.fetch_json()
            orders = self.parse_json(payload)
            return AdapterResult(self.source, "done" if orders else "empty", tuple(orders), now_iso())
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as error:
            return AdapterResult(self.source, "error", checked_at=now_iso(), error=f"Ошибка API: {error}")

    def parse_json(self, payload: dict[str, Any]) -> list[FreelanceOrder]:
        data = payload.get("data") if isinstance(payload, dict) else []
        orders: list[FreelanceOrder] = []
        for item in data if isinstance(data, list) else []:
            attributes = item.get("attributes") or {}
            external_id = str(item.get("id") or "").strip()
            title = str(attributes.get("name") or "").strip()
            if not external_id or not title:
                continue
            budget = attributes.get("budget") if isinstance(attributes.get("budget"), dict) else {}
            amount = budget.get("amount")
            link = (item.get("links") or {}).get("self") or ""
            orders.append(FreelanceOrder(
                source=self.source,
                external_id=external_id,
                title=title,
                description=str(attributes.get("description_html") or attributes.get("description") or ""),
                url=str(link),
                budget_min=int(amount) if str(amount).isdigit() else None,
                budget_text=str(amount or ""),
                currency=str(budget.get("currency") or "UAH"),
                discovered_at=now_iso(),
            ))
        return orders
