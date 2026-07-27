from __future__ import annotations

import os
import inspect
import re
from dataclasses import dataclass, replace
from typing import Any, Callable
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from ..models import AdapterResult, FreelanceOrder, FreelanceSettings
from .base import absolute_url, now_iso, order_from_card


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
        soup = BeautifulSoup(html, "html.parser")
        visible_soup = BeautifulSoup(html, "html.parser")
        for hidden in visible_soup.select("script, style, noscript, template"):
            hidden.decompose()
        visible_text = visible_soup.get_text(" ", strip=True).lower()
        if status_code in {401, 403, 429}:
            return BrowserPageState("blocked", f"Источник ограничил доступ: HTTP {status_code}")
        if any(marker in normalized_url for marker in ("login", "signin", "auth")):
            return BrowserPageState("auth_required", "Требуется вход в аккаунт", True)
        if soup.select_one('input[type="password"]') or any(marker in normalized_title for marker in ("вход", "авторизац", "sign in", "log in")):
            return BrowserPageState("auth_required", "Требуется вход в аккаунт", True)
        challenge_element = next((
            element for element in soup.find_all(True)
            if element.name not in {"script", "style", "noscript", "template"} and any(marker in " ".join((
                str(element.get("id") or ""),
                " ".join(element.get("class") or ()),
                str(element.get("src") or ""),
            )).lower() for marker in ("captcha", "challenge"))
        ), None)
        blocked_title = any(marker in normalized_title for marker in ("доступ ограничен", "access denied", "captcha", "challenge"))
        blocked_visible_page = any(marker in visible_text for marker in ("доступ ограничен", "access denied"))
        if challenge_element is not None or blocked_title or blocked_visible_page:
            return BrowserPageState("blocked", "Площадка ограничила автоматический доступ")
        if soup.select_one("[data-empty-state]") or any(marker in visible_text for marker in ("нет подходящих заказов", "заказов пока нет", "нет доступных заданий")):
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

    def wait_for_initial_state(self, page: Any) -> None:
        return None

    def empty_result_reason(self) -> tuple[str, str]:
        """Чем объяснять пустой разбор: сменившейся вёрсткой или отсутствием подходящего."""

        return "error", "Не удалось найти ленту заказов: разметка источника изменилась"

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
            if status_code not in {401, 403, 429}:
                self.wait_for_initial_state(page)
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
                status, error = self.empty_result_reason()
                return AdapterResult(self.source, status, checked_at=now_iso(), error=error)
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


def _dev_markers() -> tuple[str, ...]:
    """Категории YouDo, которые относятся к разработке.

    YouDo отдаёт вперемешку курьеров, уборку и грузоперевозки. Без фильтра база
    забивается непрофильными заданиями. Список переопределяется переменной
    FREELANCE_YOUDO_CATEGORIES, а FREELANCE_YOUDO_ALL=yes выключает фильтр совсем.
    """

    override = os.getenv("FREELANCE_YOUDO_CATEGORIES", "").strip()
    if override:
        return tuple(item.strip().lower() for item in override.split(",") if item.strip())
    return (
        "разработ", "программир", "верстк", "сайт", "веб", "приложен", "бот",
        "скрипт", "автоматизац", "интеграц", "api", "компьютерн", "it",
        "1с", "битрикс", "wordpress", "тильда", "tilda", "дизайн", "интерфейс",
        "ui", "ux", "виртуальный помощник", "seo", "база данных", "парсер",
    )


class YoudoAdapter(BrowserAdapter):
    source = "youdo"
    url = os.getenv("FREELANCE_YOUDO_URL", "https://youdo.com/tasks")
    card_selector = '[class*="TasksList_listItem__"]'
    task_card_selector = f'{card_selector}:has(a[href^="/t"])'
    show_more_selector = '[class*="TasksList_showMoreButton__"]'
    max_tasks = max(50, int(os.getenv("FREELANCE_YOUDO_MAX_TASKS", "500")))

    def __init__(self, browser_factory: Callable[..., Any] | None = None) -> None:
        super().__init__(browser_factory)
        # Сколько карточек было на странице до отбора по категориям.
        self.last_seen_cards = 0

    def empty_result_reason(self) -> tuple[str, str]:
        if self.last_seen_cards:
            return "empty", ""
        return super().empty_result_reason()

    @staticmethod
    def is_development(labels: list[str], title: str) -> bool:
        if os.getenv("FREELANCE_YOUDO_ALL", "").strip().lower() in {"1", "yes", "true"}:
            return True
        # Смотрим на метки категории; заголовок берём, только если меток нет,
        # иначе «доставить компьютер» проходил бы как компьютерная помощь.
        haystack = " ".join(labels) if labels else title
        normalized = haystack.lower().replace("ё", "е")
        return any(marker.replace("ё", "е") in normalized for marker in _dev_markers())

    def classify_html(self, status_code: int | None, title: str, page_url: str, html: str) -> BrowserPageState:
        soup = BeautifulSoup(html, "html.parser")
        has_real_tasks = any(card.select_one('a[href^="/t"]') is not None for card in soup.select(self.card_selector))
        if status_code not in {401, 403, 429} and has_real_tasks:
            return BrowserPageState("ready")
        state = super().classify_html(status_code, title, page_url, html)
        if state.status != "ready":
            return state
        if soup.select_one('[class*="TasksList_empty__"]'):
            return BrowserPageState("empty")
        return state

    def prepare_page(self, page: Any) -> None:
        tasks = page.locator(self.task_card_selector)
        stable_checks = 0
        while tasks.count() < self.max_tasks:
            show_more = page.locator(self.show_more_selector)
            if not show_more.count() or not show_more.first.is_visible():
                break
            previous_count = tasks.count()
            show_more.first.click()
            page.wait_for_timeout(1200)
            stable_checks = stable_checks + 1 if tasks.count() <= previous_count else 0
            if stable_checks >= 2:
                break

    def wait_for_initial_state(self, page: Any) -> None:
        try:
            page.locator(self.task_card_selector).first.wait_for(state="attached", timeout=10000)
        except Exception:  # noqa: BLE001 - empty lists and blocked pages have no task card
            page.wait_for_timeout(1200)

    def parse_html(self, html: str, page_url: str) -> list[FreelanceOrder]:
        soup = BeautifulSoup(html, "html.parser")
        orders: list[FreelanceOrder] = []
        seen = 0
        for card in soup.select(self.card_selector):
            link = card.select_one('a[href^="/t"]')
            if link is None:
                continue
            seen += 1
            href = str(link.get("href") or "")
            path = urlsplit(href).path
            match = re.fullmatch(r"/t(\d+)", path)
            title = link.get_text(" ", strip=True)
            if match is None or not title:
                continue
            address_node = card.select_one('[class*="TasksList_address__"]')
            date_node = card.select_one('[class*="TasksList_date__"]')
            price_node = card.select_one('[class*="TasksList_desktopPriceBlock__"] [class*="TasksList_price__"]') or card.select_one('[class*="TasksList_price__"]')
            customer_node = card.select_one('[class*="TasksList_authorName__"]')
            labels = [node.get_text(" ", strip=True) for node in card.select('[class*="TasksList_footerLabels__"] [class*="TasksList_label__"]')]
            if not self.is_development(labels, title):
                continue
            category = next((label for label in labels if label), "")
            order = order_from_card(
                self.source,
                title,
                absolute_url(page_url, path),
                address_node.get_text(" ", strip=True) if address_node else "",
                price_node.get_text(" ", strip=True) if price_node else "",
                category,
                f"youdo-{match.group(1)}",
            )
            orders.append(replace(
                order,
                customer=customer_node.get_text(" ", strip=True) if customer_node else "",
                published_at=date_node.get_text(" ", strip=True) if date_node else "",
            ))
        self.last_seen_cards = seen
        return orders

    def parse_page(self, page: Any) -> list[FreelanceOrder]:
        return self.parse_html(page.content(), str(getattr(page, "url", self.url)))

    def collect(self, settings: FreelanceSettings) -> AdapterResult:
        result = self._collect_once(settings, headless=True)
        if result.status != "blocked":
            return result
        return self._collect_once(settings, headless=False)
