from __future__ import annotations

import os
import inspect
from typing import Any, Callable

from ..models import AdapterResult, FreelanceOrder, FreelanceSettings
from .base import now_iso, order_from_card


class BrowserAdapter:
    source = ""
    requires_browser = True
    url = ""
    title_selectors = ("a[data-order-id]", "a[href*='/tasks/']", "a[href*='/orders/']")

    def __init__(self, browser_factory: Callable[..., Any] | None = None) -> None:
        self.browser_factory = browser_factory

    def _create_browser(self) -> Any:
        if self.browser_factory is None:
            return None
        try:
            parameters = inspect.signature(self.browser_factory).parameters.values()
            accepts_source = any(parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.VAR_POSITIONAL) for parameter in parameters)
        except (TypeError, ValueError):
            accepts_source = True
        return self.browser_factory(self.source) if accepts_source else self.browser_factory()

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

    def collect(self, settings: FreelanceSettings) -> AdapterResult:
        if self.browser_factory is None:
            return AdapterResult(self.source, "auth_required", checked_at=now_iso(), error="Откройте авторизацию в браузере", auth_required=True)
        try:
            browser = self._create_browser()
        except Exception as error:  # noqa: BLE001 - local browser runtime may be absent
            return AdapterResult(self.source, "error", checked_at=now_iso(), error=str(error))
        if browser is None:
            return AdapterResult(self.source, "auth_required", checked_at=now_iso(), error="Откройте авторизацию в браузере", auth_required=True)
        try:
            page = browser.new_page() if hasattr(browser, "new_page") else browser
            page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
            if any(marker in page.url.lower() for marker in ("login", "signin", "auth")):
                return AdapterResult(self.source, "auth_required", checked_at=now_iso(), error="Требуется вход в аккаунт", auth_required=True)
            orders = self.parse_page(page)
            return AdapterResult(self.source, "done" if orders else "empty", tuple(orders), now_iso())
        except Exception as error:  # noqa: BLE001 - isolate browser source failures
            return AdapterResult(self.source, "error", checked_at=now_iso(), error=str(error))
        finally:
            close = getattr(browser, "close", None)
            if callable(close):
                close()


class WorkzillaAdapter(BrowserAdapter):
    source = "workzilla"
    url = os.getenv("FREELANCE_WORKZILLA_URL", "https://client.work-zilla.com/freelancer")


class ProfiAdapter(BrowserAdapter):
    source = "profi"
    url = os.getenv("FREELANCE_PROFI_URL", "https://profi.ru/backoffice/a.php")


class YoudoAdapter(BrowserAdapter):
    source = "youdo"
    url = os.getenv("FREELANCE_YOUDO_URL", "https://youdo.com/tasks")
