from __future__ import annotations

import os
import inspect
from dataclasses import dataclass
from typing import Any, Callable

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
    url = os.getenv("FREELANCE_PROFI_URL", "https://profi.ru/backoffice/a.php")


class YoudoAdapter(BrowserAdapter):
    source = "youdo"
    url = os.getenv("FREELANCE_YOUDO_URL", "https://youdo.com/tasks")
