from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from . import storage
from .models import JOB_SOURCES, JobParseRun, JobSettings
from .scoring import score_vacancy


def settings_from_dict(value: dict[str, Any]) -> JobSettings:
    return JobSettings(
        sources=tuple(value.get("sources") or JOB_SOURCES),
        keywords=tuple(value.get("keywords") or ()),
        excluded_keywords=tuple(value.get("excluded_keywords") or ()),
        telegram_channels=tuple(value.get("telegram_channels") or ()),
        area=str(value.get("area") or "Россия"),
        salary_min=int(value.get("salary_min") or 0),
        remote_only=bool(value.get("remote_only")),
        per_source_limit=int(value.get("per_source_limit") or 50),
    )


class JobCollector:
    """Один проход по включённым источникам вакансий."""

    def __init__(self, registry: dict[str, Any]) -> None:
        self.registry = registry
        self._lock = threading.Lock()

    def is_busy(self) -> bool:
        locked = self._lock.acquire(blocking=False)
        if locked:
            self._lock.release()
            return False
        return True

    def collect(self, run: JobParseRun, settings: JobSettings) -> dict[str, Any]:
        # Один сбор за раз: параллельные проходы дублировали бы запросы к площадкам.
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Сбор вакансий уже идёт")
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            run.status = "running"
            inserted = 0
            duplicates = 0
            failures: list[str] = []

            for source in settings.sources:
                adapter = self.registry.get(source)
                if adapter is None:
                    run.source_states[source] = {"status": "error", "error": "Источник не поддерживается", "found": 0}
                    storage.record_job_source_check(source, "error", 0, "Источник не поддерживается")
                    continue

                run.message = f"Собираю вакансии: {source}"
                try:
                    result = adapter.collect(settings)
                except Exception as error:  # noqa: BLE001 - сбой площадки не должен ронять весь проход
                    run.source_states[source] = {"status": "error", "error": str(error)[:300], "found": 0}
                    storage.record_job_source_check(source, "error", 0, str(error))
                    failures.append(source)
                    continue

                source_inserted = 0
                for vacancy in result.vacancies:
                    score, reasons, match = score_vacancy(vacancy, settings)
                    try:
                        _, is_new = storage.create_job(vacancy, score, reasons, match)
                    except ValueError:
                        continue
                    if is_new:
                        inserted += 1
                        source_inserted += 1
                    else:
                        duplicates += 1

                run.source_states[source] = {
                    "status": result.status,
                    "error": result.error,
                    "found": len(result.vacancies),
                    "new": source_inserted,
                    "checked_at": result.checked_at,
                }
                storage.record_job_source_check(source, result.status, len(result.vacancies), result.error)
                if result.status == "error":
                    failures.append(source)

            run.inserted = inserted
            run.duplicates = duplicates
            if failures and inserted == 0:
                run.status = "error"
                run.error = f"Источники не ответили: {', '.join(failures)}"
                run.message = "Не удалось собрать вакансии"
            elif failures:
                run.status = "partial"
                run.message = f"Готово с ошибками: новых — {inserted}, уже были — {duplicates}. Сбой: {', '.join(failures)}"
            else:
                run.status = "done"
                run.message = f"Готово: новых — {inserted}, уже были — {duplicates}"

            storage.record_job_run(
                run.id, started_at, run.status, inserted, duplicates,
                list(settings.sources), run.message, run.error,
            )
            return run.snapshot()
        finally:
            self._lock.release()
