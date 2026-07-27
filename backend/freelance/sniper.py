from __future__ import annotations

import logging
import threading
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from .. import database
from .models import FreelanceSettings
from .scoring import score_order


logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SniperBusyError(RuntimeError):
    """Проверка уже идёт: параллельный проход занял бы тот же профиль Chrome."""


class FreelanceSniper:
    def __init__(self, registry: dict[str, Any], notifier: Any, settings: FreelanceSettings | None = None, interval_seconds: int | None = None) -> None:
        self.registry = registry
        self.notifier = notifier
        self.settings = settings or FreelanceSettings()
        resolved_interval = interval_seconds if interval_seconds is not None else self.settings.interval_seconds
        self.interval_seconds = max(30, int(resolved_interval))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._check_lock = threading.Lock()
        self._source_statuses: dict[str, dict[str, Any]] = {}
        self._status = "stopped"
        self._last_error = ""
        self._last_run_at = ""

    def set_settings(self, settings: FreelanceSettings) -> None:
        with self._lock:
            self.settings = settings
            self.interval_seconds = max(30, int(settings.interval_seconds))

    def start(self) -> dict[str, Any]:
        with self._lock:
            # Событие сбрасывается всегда: иначе перезапуск во время долгого цикла
            # оставляет взведённый флаг, и новый поток завершается сразу же.
            self._stop_event.clear()
            if not (self._thread and self._thread.is_alive()):
                self._last_error = ""
                self._thread = threading.Thread(target=self._run, daemon=True, name="semix-freelance-sniper")
                self._thread.start()
            self._status = "running"
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        with self._lock:
            self._status = "stopped"
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            alive = bool(self._thread and self._thread.is_alive())
            status = self._status
            # Поток мог умереть между циклами — не показываем «работает» мёртвому снайперу.
            if status == "running" and not alive:
                status = "error" if self._last_error else "stopped"
            return {
                "status": status,
                "sources": dict(self._source_statuses),
                "interval_seconds": self.interval_seconds,
                "last_error": self._last_error,
                "last_run_at": self._last_run_at,
                "thread_alive": alive,
            }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except SniperBusyError:
                logger.info("Пропускаю цикл снайпера: ручная проверка ещё идёт")
            except Exception as error:  # noqa: BLE001 - цикл не должен умирать молча
                logger.exception("Цикл фриланс-снайпера завершился ошибкой")
                with self._lock:
                    self._last_error = str(error)[:400]
            self._stop_event.wait(self.interval_seconds)

    def check_once(self) -> dict[str, Any]:
        if not self._check_lock.acquire(blocking=False):
            raise SniperBusyError("Проверка источников уже идёт")
        try:
            return self._check_once_locked()
        finally:
            self._check_lock.release()

    def _check_once_locked(self) -> dict[str, Any]:
        started_at = _now()
        inserted = 0
        duplicates = 0
        run_order_ids: list[int] = []
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
                    points, reasons, percent = score_order(order, settings)
                    scored = replace(order, relevance=percent, relevance_points=points, relevance_reasons=tuple(reasons))
                    was_saved = database.freelance_order_exists(scored)
                    saved = database.create_freelance_order(scored)
                    if was_saved:
                        duplicates += 1
                        continue
                    # К запуску привязываем только найденное в этом проходе, иначе
                    # таблица связей растёт на весь объём выдачи каждые 30 секунд.
                    run_order_ids.append(int(saved["id"]))
                    inserted += 1
                    if settings.telegram_enabled and not database.notification_sent(scored.source, scored.external_id, database.telegram_allowed_chat_id()):
                        if self.notifier.send_order(saved):
                            database.record_notification(scored.source, scored.external_id, database.telegram_allowed_chat_id())
                        else:
                            database.record_notification(scored.source, scored.external_id, database.telegram_allowed_chat_id(), "Telegram не подтвердил отправку")
            except Exception as error:  # noqa: BLE001 - one adapter must not stop the cycle
                logger.warning("Источник %s завершился ошибкой: %s", source, error)
                status = {"source": source, "status": "error", "checked_at": _now(), "order_count": 0, "error": str(error), "auth_required": False}
                source_results[source] = status
                database.record_source_check(status)
        statuses = list(source_results.values())
        overall = "error" if statuses and all(item["status"] == "error" for item in statuses) else "partial" if any(item["status"] == "error" for item in statuses) else "done"
        with self._lock:
            self._source_statuses = source_results
            self._last_run_at = _now()
            self._last_error = "" if overall != "error" else "Все источники вернули ошибку"
        run_id = database.record_freelance_run(
            {"started_at": started_at, "finished_at": _now(), "status": overall, "inserted": inserted, "duplicates": duplicates, "sources": source_results},
            run_order_ids,
        )
        return {"run_id": run_id, "status": overall, "inserted": inserted, "duplicates": duplicates, "sources": source_results}
