from __future__ import annotations

import os
from typing import Any, Callable

import httpx


class TelegramNotifier:
    def __init__(self, token: str | None = None, allowed_chat_id: str | None = None, transport: Callable[..., bool] | None = None) -> None:
        self.token = (token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.allowed_chat_id = (allowed_chat_id if allowed_chat_id is not None else os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "")).strip()
        self.transport = transport or self._send_http

    def _send_http(self, *, chat_id: str, text: str) -> bool:
        if not self.token:
            return False
        response = httpx.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
        response.raise_for_status()
        return bool(response.json().get("ok"))

    def send_text(self, chat_id: str, text: str) -> bool:
        target = str(chat_id).strip()
        if not self.allowed_chat_id or target != self.allowed_chat_id:
            return False
        try:
            return bool(self.transport(chat_id=target, text=text))
        except (httpx.HTTPError, ValueError):
            return False

    def send_order(self, order: dict[str, Any]) -> bool:
        budget = order.get("budget_text") or "Бюджет не указан"
        source = order.get("source") or "Источник не указан"
        title = order.get("title") or "Новый заказ"
        description = str(order.get("description") or "").strip()
        description = description[:500] + ("…" if len(description) > 500 else "")
        text = f"Новый заказ · {source}\n\n{title}\nБюджет: {budget}\nРелевантность: {order.get('relevance', 0)}%"
        if description:
            text += f"\n\n{description}"
        if order.get("url"):
            text += f"\n\n{order['url']}"
        return self.send_text(self.allowed_chat_id, text)
