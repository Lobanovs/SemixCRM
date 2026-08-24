from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import database
from .freelance.models import FREELANCE_SOURCES, FreelanceOrderFilters
from .jobs import storage as jobs_storage
from .jobs.models import JOB_SOURCES
from .jobs.storage import JobFilters


ATTENTION_STATUSES = {"error", "blocked", "auth_required"}
STALE_AFTER = timedelta(hours=48)


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_health(
    *,
    kind: str,
    sources: tuple[str, ...],
    statuses: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    known = {str(item.get("source") or ""): item for item in statuses}
    result: list[dict[str, Any]] = []
    for source in sources:
        item = known.get(source, {})
        checked_at = str(item.get("checked_at") or "")
        checked = _parse_datetime(checked_at)
        status = str(item.get("status") or "idle").lower()
        failed = status in ATTENTION_STATUSES or bool(item.get("auth_required"))
        stale = checked is not None and now - checked > STALE_AFTER
        if failed:
            state = "error"
        elif checked is None:
            state = "never"
        elif stale:
            state = "stale"
        else:
            state = "healthy"
        result.append({
            "kind": kind,
            "source": source,
            "status": status,
            "state": state,
            "checked_at": checked_at,
            "error": str(item.get("error") or ""),
            "is_stale": stale,
            "needs_attention": state != "healthy",
        })
    return result


def _client_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(item["id"]),
        "name": str(item.get("name") or "Без названия"),
        "niche": str(item.get("niche") or item.get("category") or ""),
        "city": str(item.get("city") or ""),
        "score": int(item.get("lead_score") or 0),
        "score_max": int(item.get("lead_score_max") or 100),
        "rating": item.get("rating"),
        "reviews": int(item.get("reviews") or 0),
        "phone": str(item.get("phone") or ""),
    }


def _task_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(item["id"]),
        "title": str(item.get("title") or "Задача"),
        "date": str(item.get("date") or item.get("task_date") or ""),
        "time": str(item.get("time") or item.get("task_time") or ""),
        "kind": str(item.get("kind") or "task"),
    }


def _job_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(item["id"]),
        "role": str(item.get("role") or "Вакансия"),
        "company": str(item.get("company") or "Компания не указана"),
        "source": str(item.get("source") or ""),
        "relevance": int(item.get("relevance") or 0),
        "salary_text": str(item.get("salary_text") or ""),
        "discovered_at": str(item.get("discovered_at") or ""),
    }


def _freelance_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(item["id"]),
        "title": str(item.get("title") or "Заказ"),
        "source": str(item.get("source") or ""),
        "relevance": int(item.get("relevance") or 0),
        "budget_text": str(item.get("budget_text") or ""),
        "published_at": str(item.get("published_at") or item.get("discovered_at") or ""),
    }


def build_dashboard(now: datetime | None = None, limit: int = 5) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    bounded_limit = max(1, min(int(limit), 20))
    week_start = (current.date() - timedelta(days=current.weekday())).isoformat()

    client_items = database.list_clients()
    client_summary = database.client_stats()
    schedule = database.get_schedule(week_start)
    freelance_items = database.list_freelance_orders(FreelanceOrderFilters(status="Новый", sort="relevance"))
    freelance_summary = database.freelance_stats()
    job_items = jobs_storage.list_jobs(JobFilters(status="Сохранено", sort="relevance"))
    job_summary = jobs_storage.job_stats()

    new_clients = [item for item in client_items if item.get("status") == "Новый"]
    open_tasks = [item for item in schedule.get("tasks", []) if not item.get("done")]
    health = [
        *_source_health(
            kind="freelance",
            sources=FREELANCE_SOURCES,
            statuses=database.list_source_statuses(),
            now=current,
        ),
        *_source_health(
            kind="jobs",
            sources=JOB_SOURCES,
            statuses=jobs_storage.list_job_source_statuses(),
            now=current,
        ),
    ]
    health.sort(key=lambda item: (not item["needs_attention"], item["kind"], item["source"]))

    client_stages = client_summary.get("stages", {})
    job_stages = job_summary.get("stages", {})
    return {
        "generated_at": current.isoformat(),
        "stats": {
            "clients_total": int(client_summary.get("total") or len(client_items)),
            "clients_to_contact": int(client_stages.get("Новый") or len(new_clients)),
            "tasks_open": len(open_tasks),
            "jobs_new": int(job_stages.get("Сохранено") or len(job_items)),
            "freelance_active": int(freelance_summary.get("total") or len(freelance_items)),
        },
        "clients": [_client_item(item) for item in new_clients[:bounded_limit]],
        "tasks": [_task_item(item) for item in open_tasks[:bounded_limit]],
        "jobs": [_job_item(item) for item in job_items[:bounded_limit]],
        "freelance": [_freelance_item(item) for item in freelance_items[:bounded_limit]],
        "source_health": health,
    }
