from __future__ import annotations

import os
import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable

from bs4 import BeautifulSoup

from ..models import AdapterResult, FreelanceOrder, FreelanceSettings
from .base import now_iso, order_from_card


@dataclass(frozen=True)
class BrowserPageState:
    status: str
    error: str = ""
    auth_required: bool = False


class BrowserAdapter:
    source = ""
    requires_browser = True
    url = ""
    title_selectors = ("a[data-order-id]", "a[href*='/tasks/']", "a[href*='/orders/']")

    def __init__(self, browser_factory: Callable[..., Any] | None = None) -> None:
        self.browser_factory = browser_factory

    def _create_browser(self, *, headless: bool = True) -> Any:
        if self.browser_factory is None:
            return None
        try:
            parameters = list(inspect.signature(self.browser_factory).parameters.values())
            positional = [parameter for parameter in parameters if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
            has_varargs = any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters)
        except (TypeError, ValueError):
            return self.browser_factory(self.source, headless)
        if has_varargs or len(positional) >= 2:
            return self.browser_factory(self.source, headless)
        if positional:
            return self.browser_factory(self.source)
        return self.browser_factory()

    def classify_html(self, status_code: int | None, title: str, page_url: str, html: str) -> BrowserPageState:
        normalized_url = page_url.lower()
        normalized_title = title.lower()
        normalized_html = html.lower()
        if status_code in {401, 403, 429}:
            return BrowserPageState("blocked", f"Источник ограничил доступ: HTTP {status_code}")
        if any(marker in normalized_url for marker in ("login", "signin", "auth")):
            return BrowserPageState("auth_required", "Требуется вход в аккаунт", True)
        if "type='password'" in normalized_html or 'type="password"' in normalized_html or any(marker in normalized_title for marker in ("вход", "авторизац", "sign in", "log in")):
            return BrowserPageState("auth_required", "Требуется вход в аккаунт", True)
        if any(marker in f"{normalized_title}\n{normalized_html}" for marker in ("доступ ограничен", "access denied", "captcha", "challenge")):
            return BrowserPageState("blocked", "Площадка ограничила автоматический доступ")
        if "data-empty-state" in normalized_html or any(marker in normalized_html for marker in ("нет подходящих заказов", "заказов пока нет", "нет доступных заданий")):
            return BrowserPageState("empty")
        return BrowserPageState("ready")

    def parse_page(self, page: Any) -> list[FreelanceOrder]:
        rows = page.locator("[data-order-id], [data-task-id], article").all()
        orders: list[FreelanceOrder] = []
        for row in rows:
            title = row.inner_text().strip().splitlines()[0] if row.inner_text().strip() else ""
            link = row.locator("a").first.get_attribute("href") if row.locator("a").count() else ""
            if not title or not link:
                continue
            orders.append(order_from_card(self.source, title, link, row.inner_text()))
        return orders

    def prepare_page(self, page: Any) -> None:
        return None

    def _collect_once(self, settings: FreelanceSettings, *, headless: bool = True) -> AdapterResult:
        if self.browser_factory is None:
            return AdapterResult(self.source, "auth_required", checked_at=now_iso(), error="Откройте авторизацию в браузере", auth_required=True)
        try:
            browser = self._create_browser(headless=headless)
        except Exception as error:  # noqa: BLE001 - local browser runtime may be absent
            return AdapterResult(self.source, "error", checked_at=now_iso(), error=str(error))
        if browser is None:
            return AdapterResult(self.source, "auth_required", checked_at=now_iso(), error="Откройте авторизацию в браузере", auth_required=True)
        try:
            page = browser.new_page() if hasattr(browser, "new_page") else browser
            response = page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
            status_code = getattr(response, "status", None)
            title_method = getattr(page, "title", None)
            content_method = getattr(page, "content", None)
            title = str(title_method() if callable(title_method) else "")
            html = str(content_method() if callable(content_method) else "")
            state = self.classify_html(status_code, title, str(getattr(page, "url", self.url)), html)
            if state.status != "ready":
                return AdapterResult(self.source, state.status, checked_at=now_iso(), error=state.error, auth_required=state.auth_required)
            self.prepare_page(page)
            title = str(title_method() if callable(title_method) else "")
            html = str(content_method() if callable(content_method) else "")
            state = self.classify_html(status_code, title, str(getattr(page, "url", self.url)), html)
            if state.status != "ready":
                return AdapterResult(self.source, state.status, checked_at=now_iso(), error=state.error, auth_required=state.auth_required)
            orders = self.parse_page(page)
            if not orders:
                return AdapterResult(self.source, "error", checked_at=now_iso(), error="Не удалось найти ленту заказов: разметка источника изменилась")
            return AdapterResult(self.source, "done", tuple(orders), now_iso())
        except Exception as error:  # noqa: BLE001 - isolate browser source failures
            return AdapterResult(self.source, "error", checked_at=now_iso(), error=str(error))
        finally:
            close = getattr(browser, "close", None)
            if callable(close):
                close()

    def collect(self, settings: FreelanceSettings) -> AdapterResult:
        return self._collect_once(settings, headless=True)


class ProfiAdapter(BrowserAdapter):
    source = "profi"
    url = os.getenv("FREELANCE_PROFI_URL", "https://profi.ru/backoffice/n.php")
    card_selector = '[data-testid$="_order-snippet"]'

    def classify_html(self, status_code: int | None, title: str, page_url: str, html: str) -> BrowserPageState:
        state = super().classify_html(status_code, title, page_url, html)
        if state.status != "ready":
            return state
        soup = BeautifulSoup(html, "html.parser")
        if soup.select_one('[data-testid="ORDERS_BOARD_EMPTY"]'):
            return BrowserPageState("empty")
        return state

    def prepare_page(self, page: Any) -> None:
        cards = page.locator(self.card_selector)
        previous_count = -1
        stable_checks = 0
        for _ in range(30):
            count = cards.count()
            stable_checks = stable_checks + 1 if count == previous_count else 0
            previous_count = count
            if stable_checks >= 5:
                break
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1200)

    def parse_html(self, html: str, page_url: str) -> list[FreelanceOrder]:
        soup = BeautifulSoup(html, "html.parser")
        orders: list[FreelanceOrder] = []
        for card in soup.select(self.card_selector):
            test_id = str(card.get("data-testid") or "")
            match = re.fullmatch(r"(\d+)_order-snippet", test_id)
            title_node = card.select_one("h3")
            if match is None or title_node is None:
                continue
            external_number = match.group(1)
            title = title_node.get_text(" ", strip=True)
            if not title:
                continue
            description_node = card.select_one("p")
            description = description_node.get_text(" ", strip=True) if description_node else ""
            budget_text = ""
            category = ""
            for item in card.select("li"):
                label = str(item.get("aria-label") or "").lower()
                value = item.get_text(" ", strip=True)
                if "бюджет" in label or "стоим" in label or "₽" in value:
                    budget_text = value
                elif "категор" in label or "услуг" in label:
                    category = value
            href = f"https://profi.ru/backoffice/n.php?o={external_number}"
            orders.append(order_from_card(
                self.source,
                title,
                href,
                description,
                budget_text,
                category,
                f"profi-{external_number}",
            ))
        return orders

    def parse_page(self, page: Any) -> list[FreelanceOrder]:
        return self.parse_html(page.content(), str(getattr(page, "url", self.url)))


class YoudoAdapter(BrowserAdapter):
    source = "youdo"
    url = os.getenv("FREELANCE_YOUDO_URL", "https://youdo.com/tasks")
