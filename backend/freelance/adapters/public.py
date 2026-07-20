from __future__ import annotations

import json
import re
from dataclasses import replace
from html import unescape
from typing import Any

from bs4 import BeautifulSoup

from ..models import FreelanceOrder
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

class KworkAdapter(PublicHttpAdapter):
    source = "kwork"
    url = source_url("kwork", "https://kwork.ru/projects")

    def parse_html(self, html: str) -> list[FreelanceOrder]:
        marker = "window.stateData="
        start = html.find(marker)
        if start < 0:
            return []
        try:
            payload, _ = json.JSONDecoder().raw_decode(html[start + len(marker):])
        except json.JSONDecodeError:
            return []
        wants = payload.get("wants") or (payload.get("wantsListData") or {}).get("wants") or []
        categories = payload.get("categories") or {}
        orders: list[FreelanceOrder] = []
        for item in wants if isinstance(wants, list) else []:
            external_id = str(item.get("id") or "").strip()
            title = str(item.get("name") or "").strip()
            if not external_id or not title:
                continue
            raw_budget = str(item.get("priceLimit") or "").strip()
            try:
                budget = int(float(raw_budget)) if raw_budget else None
            except ValueError:
                budget = None
            customer = str((item.get("user") or {}).get("username") or "").strip()
            category = self._category_name(categories, str(item.get("category_id") or ""))
            description = BeautifulSoup(unescape(str(item.get("description") or "")), "html.parser").get_text(" ", strip=True)
            orders.append(FreelanceOrder(
                source=self.source,
                external_id=f"kwork-{external_id}",
                title=title,
                description=description,
                url=f"https://kwork.ru/projects/{external_id}/view",
                customer=customer,
                categories=(category,) if category else (),
                budget_min=budget,
                budget_text=f"{budget:,} ₽".replace(",", " ") if budget is not None else "",
                published_at=str(item.get("date_create") or ""),
                discovered_at=now_iso(),
            ))
        return orders

    @classmethod
    def _category_name(cls, value: Any, category_id: str) -> str:
        if isinstance(value, dict):
            direct = value.get(category_id)
            if isinstance(direct, dict):
                name = direct.get("name") or direct.get("title")
                if name:
                    return str(name)
            for nested in value.values():
                name = cls._category_name(nested, category_id)
                if name:
                    return name
        elif isinstance(value, list):
            for nested in value:
                if isinstance(nested, dict) and str(nested.get("id") or "") == category_id:
                    name = nested.get("name") or nested.get("title")
                    if name:
                        return str(name)
                name = cls._category_name(nested, category_id)
                if name:
                    return name
        return ""


class FreelanceRuAdapter(PublicHttpAdapter):
    source = "freelance_ru"
    url = source_url("freelance_ru", "https://freelance.ru/task")

    def parse_html(self, html: str) -> list[FreelanceOrder]:
        soup = BeautifulSoup(html, "html.parser")
        orders: list[FreelanceOrder] = []
        for card in soup.select("article.task-card"):
            link = card.select_one("a.task-card__title-link[href]")
            if link is None:
                continue
            href = absolute_url(self.url, str(link.get("href") or ""))
            title = link.get_text(" ", strip=True)
            match = re.search(r"/task/view/(\d+)", href)
            if not title or not match:
                continue
            description = card.select_one(".task-card__desc")
            budget = card.select_one(".task-card__budget")
            category = card.select_one(".task-chip--cat")
            published = card.select_one(".task-card__foot-item")
            order = order_from_card(
                self.source,
                title,
                href,
                description.get_text(" ", strip=True) if description else "",
                budget.get_text(" ", strip=True) if budget else "",
                category.get_text(" ", strip=True) if category else "",
                f"freelance_ru-{match.group(1)}",
            )
            orders.append(replace(order, published_at=published.get_text(" ", strip=True) if published else ""))
        return orders
