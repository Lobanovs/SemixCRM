from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from .. import database
from .models import FreelanceOrder, FreelanceSettings
from .scoring import score_order


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FreelanceSniper:
    def __init__(self, registry: dict[str, Any], notifier: Any, settings: FreelanceSettings | None = None, interval_seconds: int = 60) -> None:
        self.registry = registry
        self.notifier = notifier
        self.settings = settings or FreelanceSettings()
        self.interval_seconds = max(30, int(interval_seconds))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._source_statuses: dict[str, dict[str, Any]] = {}
        self._status = "stopped"

    def set_settings(self, settings: FreelanceSettings) -> None:
        with self._lock:
            self.settings = settings
            self.interval_seconds = max(30, int(settings.interval_seconds))

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._status = "running"
                already_running = True
            else:
                already_running = False
                self._stop_event.clear()
                self._status = "running"
                self._thread = threading.Thread(target=self._run, daemon=True, name="semix-freelance-sniper")
                self._thread.start()
        if already_running:
            return self.status()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        with self._lock:
            self._status = "stopped"
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"status": self._status, "sources": dict(self._source_statuses), "interval_seconds": self.interval_seconds}

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(self.interval_seconds)

    def check_once(self) -> dict[str, Any]:
        inserted = 0
        duplicates = 0
        source_results: dict[str, dict[str, Any]] = {}
        settings = self.settings
        for source in settings.sources:
            adapter = self.registry.get(source)
            if adapter is None:
                source_results[source] = {"source": source, "status": "error", "error": "Источник не настроен", "checked_at": _now()}
                database.record_source_check(source_results[source])
                continue
            try:
                result = adapter.collect(settings)
                status = {"source": result.source, "status": result.status, "checked_at": result.checked_at or _now(), "order_count": len(result.orders), "error": result.error, "auth_required": result.auth_required}
                source_results[source] = status
                database.record_source_check(status)
                for order in result.orders:
                    score, reasons = score_order(order, settings)
                    scored = replace(order, relevance=score, relevance_reasons=tuple(reasons))
                    was_saved = database.freelance_order_exists(scored)
                    saved = database.create_freelance_order(scored)
                    if was_saved:
                        duplicates += 1
                        continue
                    inserted += 1
                    if settings.telegram_enabled and not database.notification_sent(scored.source, scored.external_id, database.telegram_allowed_chat_id()):
                        if self.notifier.send_order(saved):
                            database.record_notification(scored.source, scored.external_id, database.telegram_allowed_chat_id())
                        else:
                            database.record_notification(scored.source, scored.external_id, database.telegram_allowed_chat_id(), "Telegram не подтвердил отправку")
            except Exception as error:  # noqa: BLE001 - one adapter must not stop the cycle
                status = {"source": source, "status": "error", "checked_at": _now(), "order_count": 0, "error": str(error), "auth_required": False}
                source_results[source] = status
                database.record_source_check(status)
        statuses = list(source_results.values())
        overall = "error" if statuses and all(item["status"] == "error" for item in statuses) else "partial" if any(item["status"] == "error" for item in statuses) else "done"
        with self._lock:
            self._source_statuses = source_results
        return {"status": overall, "inserted": inserted, "duplicates": duplicates, "sources": source_results}
