from __future__ import annotations

import logging
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import (
    client_stats,
    create_parser_run,
    archive_all_clients,
    archive_client,
    get_parser_settings,
    init_db,
    insert_clients,
    list_clients,
    list_archived_clients,
    list_parser_runs,
    save_parser_settings,
    save_parser_run_results,
    get_parser_run,
    restore_all_clients,
    restore_client,
    update_client_status,
    update_parser_run,
    create_schedule_task,
    update_schedule_task,
    delete_schedule_task,
    get_schedule,
    save_schedule_note,
    save_schedule_week,
    archive_freelance_order,
    cleanup_freelance_orders,
    create_freelance_order,
    freelance_stats,
    preview_freelance_cleanup,
    restore_all_freelance_orders,
    get_freelance_settings,
    list_freelance_orders,
    list_source_statuses,
    list_freelance_runs,
    get_freelance_run,
    rescore_freelance_orders,
    save_freelance_settings,
    update_freelance_order,
)
from .parser import collect_leads
from .lead_utils import contacts_from_lead, is_real_website
from .freelance.adapters.registry import build_adapters
from .freelance.browser_profile import AUTH_URLS, open_login_window, persistent_browser_factory
from .freelance.models import (
    FREELANCE_SOURCES,
    FREELANCE_STATUSES,
    FreelanceCleanupRules,
    FreelanceOrder,
    FreelanceOrderFilters,
    FreelanceSettings,
)
from .freelance.scoring import FREELANCE_SCORE_MAX, score_order
from .freelance.sniper import FreelanceSniper, SniperBusyError
from .freelance.telegram import TelegramNotifier
from .jobs import storage as jobs_storage
from .jobs.adapters.registry import build_job_adapters
from .jobs.collector import JobCollector, settings_from_dict as job_settings_from_dict
from .jobs.models import JOB_SOURCES, JOB_STATUSES, JobParseRun, JobSettings, JobVacancy
from .jobs.scoring import score_vacancy
from .projects import storage as projects_storage
from .projects.detect import detect_project
from .projects.models import PROJECT_CATEGORIES, PROJECT_STATUSES, Project
from .projects.runner import ProjectRunner
from .ai.client import AiClient, AiDisabledError, AiError, AiSettings
from .ai.outreach import (
    build_input as build_ai_input,
    generate_client_message,
    _channel_links as ai_channel_links,
)
from .ai.profile import ExecutorProfile, get_profile as get_ai_profile, init_profile_schema, save_profile as save_ai_profile
from .ai.storage import forget_result as forget_ai_result, get_cached as get_cached_ai_result, init_ai_schema, input_hash as ai_input_hash
from .ai.settings import (
    DEFAULT_BASE_URL as OPENCODE_GO_BASE_URL,
    init_settings_schema as init_ai_settings_schema,
    remove_saved_key as remove_ai_settings_key,
    resolved_settings as resolve_ai_settings,
    safe_settings as get_safe_ai_settings,
    save_settings as save_ai_settings,
    validate_settings_values,
)


logger = logging.getLogger(__name__)


class ParseRequest(BaseModel):
    city: str = Field(default="Москва", min_length=2, max_length=80)
    niche: str | None = Field(default=None, min_length=2, max_length=120)
    niches: list[str] | None = None
    source: str | None = Field(default=None, max_length=20)
    sources: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=50)
    start_page: int = Field(default=1, ge=1, le=999)

    def normalized_niches(self) -> list[str]:
        values = self.niches or ([self.niche] if self.niche else [])
        return [value.strip() for value in values if value and value.strip()]

    def normalized_sources(self) -> list[str]:
        values = self.sources or ([self.source] if self.source else [])
        return [value.strip().lower() for value in values if value and value.strip()]


@dataclass
class ParserJob:
    id: str
    city: str
    niches: list[str]
    sources: list[str]
    limit: int
    start_page: int = 1
    status: str = "pending"
    message: str = "Подготовка парсера"
    error: str = ""
    count: int = 0
    skipped_count: int = 0
    clients: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "message": self.message,
            "error": self.error,
            "count": self.count,
            "skipped_count": self.skipped_count,
            "clients": self.clients,
            "city": self.city,
            "niches": self.niches,
            "sources": self.sources,
            "limit": self.limit,
            "start_page": self.start_page,
        }


ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    # Собственный origin backend нужен, чтобы работала кнопка «Try it out» в Swagger UI.
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
REQUESTED_WITH = "SemixCRM"


def guard_origin(request: Request) -> None:
    """Отсекает запросы со сторонних сайтов.

    CORS прячет ответ, но не мешает браузеру отправить «простой» POST. Без этой
    проверки любая открытая вкладка могла бы запускать парсеры и процессы проектов.
    """

    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin", "")
    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Запрос с постороннего источника отклонён")


def guard_powerful_action(request: Request) -> None:
    """Дополнительная защита для маршрутов, которые запускают процессы и браузеры."""

    guard_origin(request)
    if request.headers.get("x-requested-with", "") != REQUESTED_WITH:
        raise HTTPException(
            status_code=403,
            detail=f"Действие требует заголовок X-Requested-With: {REQUESTED_WITH}",
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    global freelance_sniper
    init_db()
    projects_storage.init_projects_schema()
    jobs_storage.init_jobs_schema()
    init_profile_schema()
    init_ai_schema()
    init_ai_settings_schema()
    settings = get_freelance_settings()
    # Заказы, сохранённые до появления объяснимой шкалы, получают очки и причины.
    rescored = rescore_freelance_orders(
        lambda order: score_order(order, _freelance_settings_from_dict(settings))
    )
    if rescored:
        logger.info("Пересчитан рейтинг заказов: %s", rescored)
    freelance_sniper = FreelanceSniper(
        registry=build_adapters(browser_factory=persistent_browser_factory),
        notifier=TelegramNotifier(),
        settings=_freelance_settings_from_dict(settings),
    )
    if settings.get("sniper_enabled"):
        freelance_sniper.start()
    try:
        yield
    finally:
        if freelance_sniper:
            freelance_sniper.stop()
        stopped = project_runner.stop_all()
        if stopped:
            logger.info("Остановлено запущенных проектов: %s", stopped)


app = FastAPI(
    title="Semix CRM API",
    version="0.3.0",
    lifespan=lifespan,
    dependencies=[Depends(guard_origin)],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
jobs: dict[str, ParserJob] = {}
jobs_lock = threading.Lock()
PARSE_JOB_HISTORY_LIMIT = 20
freelance_sniper: FreelanceSniper | None = None
project_runner = ProjectRunner()
job_collector = JobCollector(build_job_adapters())
job_runs: dict[str, JobParseRun] = {}
job_runs_lock = threading.Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "semix-crm"}


class FreelanceOrderCreateRequest(BaseModel):
    source: str = Field(default="manual", max_length=40)
    external_id: str = Field(default="", max_length=200)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=5000)
    url: str = Field(default="", max_length=1000)
    customer: str = Field(default="", max_length=200)
    categories: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=30)
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    currency: str = Field(default="RUB", max_length=8)
    budget_text: str = Field(default="", max_length=120)
    published_at: str = Field(default="", max_length=80)


class FreelanceOrderUpdateRequest(BaseModel):
    status: str | None = Field(default=None, max_length=30)
    next_step: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=2000)
    archived: bool | None = None


class FreelanceSettingsRequest(BaseModel):
    sources: list[str] = Field(min_length=1, max_length=5)
    keywords: list[str] = Field(default_factory=list, max_length=50)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=50)
    categories: list[str] = Field(default_factory=list, max_length=30)
    min_budget: int = Field(default=0, ge=0, le=100000000)
    interval_seconds: int = Field(default=60, ge=30, le=3600)
    sniper_enabled: bool = False
    telegram_enabled: bool = False


def _freelance_settings_from_dict(value: dict[str, Any]) -> FreelanceSettings:
    return FreelanceSettings(
        sources=tuple(value.get("sources") or FREELANCE_SOURCES),
        keywords=tuple(value.get("keywords") or ()),
        excluded_keywords=tuple(value.get("excluded_keywords") or ()),
        categories=tuple(value.get("categories") or ()),
        min_budget=int(value.get("min_budget") or 0),
        interval_seconds=int(value.get("interval_seconds") or 60),
        sniper_enabled=bool(value.get("sniper_enabled")),
        telegram_enabled=bool(value.get("telegram_enabled")),
    )


def _require_freelance_sniper() -> FreelanceSniper:
    if freelance_sniper is None:
        raise HTTPException(status_code=503, detail="Снайпер ещё запускается")
    return freelance_sniper


@app.get("/api/freelance/orders")
def freelance_orders(
    query: str = Query(default="", max_length=120),
    source: str = Query(default="", max_length=40),
    status: str = Query(default="", max_length=30),
    category: str = Query(default="", max_length=80),
    min_budget: int | None = Query(default=None, ge=0),
    sort: str = Query(default="relevance", max_length=20),
    archived: bool = Query(default=False),
) -> dict[str, Any]:
    orders = list_freelance_orders(FreelanceOrderFilters(query=query, source=source, status=status, category=category, min_budget=min_budget, sort=sort, include_archived=archived))
    return {
        "orders": orders,
        "stats": freelance_stats(),
        "sources": list_source_statuses(),
        "relevance_max": FREELANCE_SCORE_MAX,
    }


@app.post("/api/freelance/orders", status_code=201)
def add_freelance_order(request: FreelanceOrderCreateRequest) -> dict[str, Any]:
    try:
        order = FreelanceOrder(
            source=request.source, external_id=request.external_id, title=request.title, description=request.description,
            url=request.url, customer=request.customer, categories=tuple(request.categories), tags=tuple(request.tags),
            budget_min=request.budget_min, budget_max=request.budget_max, currency=request.currency,
            budget_text=request.budget_text, published_at=request.published_at,
        )
        return create_freelance_order(order)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.put("/api/freelance/orders/{order_id}")
def edit_freelance_order(order_id: int, request: FreelanceOrderUpdateRequest) -> dict[str, Any]:
    try:
        order = update_freelance_order(order_id, status=request.status, next_step=request.next_step, note=request.note, archived=request.archived)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order


@app.delete("/api/freelance/orders/{order_id}")
def remove_freelance_order(order_id: int) -> dict[str, Any]:
    if not archive_freelance_order(order_id):
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return {"ok": True, "archived_id": order_id}


class FreelanceCleanupRequest(BaseModel):
    """Правила массовой уборки списка заказов."""

    max_relevance: int | None = Field(default=None, ge=0, le=100)
    older_than_days: int | None = Field(default=None, ge=0, le=365)
    sources: list[str] = Field(default_factory=list, max_length=len(FREELANCE_SOURCES) + 1)
    statuses: list[str] = Field(default_factory=list, max_length=len(FREELANCE_STATUSES))
    keep_worked: bool = True
    include_everything: bool = False
    preview: bool = False


@app.post("/api/freelance/orders/cleanup", dependencies=[Depends(guard_powerful_action)])
def cleanup_freelance_list(request: FreelanceCleanupRequest) -> dict[str, Any]:
    if any(source not in (*FREELANCE_SOURCES, "manual") for source in request.sources):
        raise HTTPException(status_code=422, detail="Неизвестный источник заказов")
    if any(status not in FREELANCE_STATUSES for status in request.statuses):
        raise HTTPException(status_code=422, detail="Неизвестный статус заказа")
    rules = FreelanceCleanupRules(
        max_relevance=request.max_relevance,
        older_than_days=request.older_than_days,
        sources=tuple(request.sources),
        statuses=tuple(request.statuses),
        keep_worked=request.keep_worked,
        include_everything=request.include_everything,
    )
    if request.preview:
        return {"preview": True, **preview_freelance_cleanup(rules)}
    archived = cleanup_freelance_orders(rules)
    return {"preview": False, "archived_count": archived, "stats": freelance_stats()}


@app.post("/api/freelance/orders/restore-all", dependencies=[Depends(guard_powerful_action)])
def restore_all_freelance_list() -> dict[str, Any]:
    return {"ok": True, "restored_count": restore_all_freelance_orders(), "stats": freelance_stats()}


@app.get("/api/freelance/settings")
def freelance_settings() -> dict[str, Any]:
    return get_freelance_settings()


@app.put("/api/freelance/settings")
def update_freelance_settings(request: FreelanceSettingsRequest) -> dict[str, Any]:
    if any(source not in FREELANCE_SOURCES for source in request.sources):
        raise HTTPException(status_code=422, detail="Неизвестный источник заказов")
    try:
        settings = FreelanceSettings(
            sources=tuple(request.sources), keywords=tuple(request.keywords), excluded_keywords=tuple(request.excluded_keywords),
            categories=tuple(request.categories), min_budget=request.min_budget, interval_seconds=request.interval_seconds,
            sniper_enabled=request.sniper_enabled, telegram_enabled=request.telegram_enabled,
        )
        saved = save_freelance_settings(settings)
        sniper = _require_freelance_sniper()
        sniper.set_settings(_freelance_settings_from_dict(saved))
        if request.sniper_enabled:
            sniper.start()
        else:
            sniper.stop()
        return saved
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/freelance/sources")
def freelance_sources() -> dict[str, Any]:
    return {"sources": list_source_statuses(), "available": list(FREELANCE_SOURCES)}


@app.get("/api/freelance/sniper/status")
def freelance_sniper_status() -> dict[str, Any]:
    return _require_freelance_sniper().status()


@app.post("/api/freelance/sniper/start")
def start_freelance_sniper() -> dict[str, Any]:
    sniper = _require_freelance_sniper()
    saved = save_freelance_settings(_freelance_settings_from_dict({**get_freelance_settings(), "sniper_enabled": True}))
    sniper.set_settings(_freelance_settings_from_dict(saved))
    return sniper.start()


@app.post("/api/freelance/sniper/stop")
def stop_freelance_sniper() -> dict[str, Any]:
    sniper = _require_freelance_sniper()
    saved = save_freelance_settings(_freelance_settings_from_dict({**get_freelance_settings(), "sniper_enabled": False}))
    sniper.set_settings(_freelance_settings_from_dict(saved))
    return sniper.stop()


@app.post("/api/freelance/sniper/check", dependencies=[Depends(guard_powerful_action)])
def check_freelance_sniper() -> dict[str, Any]:
    try:
        return _require_freelance_sniper().check_once()
    except SniperBusyError as error:
        # Второй параллельный проход занял бы тот же профиль Chrome и сломал обе проверки.
        raise HTTPException(status_code=409, detail="Проверка источников уже идёт") from error


@app.get("/api/freelance/runs")
def freelance_runs() -> dict[str, Any]:
    return {"runs": list_freelance_runs()}


@app.get("/api/freelance/runs/{run_id}")
def freelance_run_detail(run_id: int) -> dict[str, Any]:
    run = get_freelance_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return run


@app.post("/api/freelance/sources/{source}/auth", dependencies=[Depends(guard_powerful_action)])
def freelance_source_auth(source: str) -> dict[str, Any]:
    if source not in FREELANCE_SOURCES:
        raise HTTPException(status_code=404, detail="Источник не найден")
    if source not in AUTH_URLS:
        raise HTTPException(status_code=422, detail="Для этого источника отдельный вход не требуется")
    try:
        return {
            **open_login_window(source),
            "message": "Войдите в аккаунт в открывшемся окне и затем закройте окно браузера.",
        }
    except (OSError, RuntimeError) as error:
        # Текст ошибки Playwright содержит локальные пути — пишем его в лог, а не в ответ.
        logger.warning("Не удалось открыть окно входа для %s: %s", source, error)
        raise HTTPException(status_code=503, detail="Не удалось открыть окно браузера для входа") from error


class ScheduleTaskCreateRequest(BaseModel):
    task_date: str = Field(min_length=10, max_length=10)
    title: str = Field(min_length=1, max_length=240)
    task_time: str = Field(default="", max_length=5)
    kind: str = Field(default="task", max_length=20)


class ScheduleTaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    task_date: str | None = Field(default=None, max_length=10)
    task_time: str | None = Field(default=None, max_length=5)
    kind: str | None = Field(default=None, max_length=20)
    done: bool | None = None


class ScheduleNoteRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class ScheduleWeekRequest(BaseModel):
    summary: str = Field(default="", max_length=2000)
    goals: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    focus: str = Field(default="", max_length=160)


def _current_week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


@app.get("/api/schedule")
def schedule(week_start: str | None = None) -> dict[str, Any]:
    try:
        return get_schedule(week_start or _current_week_start())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/schedule/tasks")
def add_schedule_task(request: ScheduleTaskCreateRequest) -> dict[str, Any]:
    try:
        return create_schedule_task(request.task_date, request.title, request.task_time, request.kind)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.put("/api/schedule/tasks/{task_id}")
def edit_schedule_task(task_id: int, request: ScheduleTaskUpdateRequest) -> dict[str, Any]:
    try:
        task = update_schedule_task(task_id, request.title, request.task_date, request.task_time, request.kind, request.done)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@app.delete("/api/schedule/tasks/{task_id}")
def remove_schedule_task(task_id: int) -> dict[str, Any]:
    if not delete_schedule_task(task_id):
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return {"ok": True, "deleted_id": task_id}


@app.put("/api/schedule/notes/{day_date}")
def update_schedule_note(day_date: str, request: ScheduleNoteRequest) -> dict[str, Any]:
    try:
        return save_schedule_note(day_date, request.note)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.put("/api/schedule/weeks/{week_start}")
def update_schedule_week(week_start: str, request: ScheduleWeekRequest) -> dict[str, Any]:
    try:
        return save_schedule_week(week_start, request.summary, request.goals, request.focus)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/clients")
def clients() -> dict[str, Any]:
    return {"clients": list_clients(), "stats": client_stats()}


@app.get("/api/clients/archived")
def archived_clients() -> dict[str, Any]:
    archived = list_archived_clients()
    return {"clients": archived, "count": len(archived)}


class ClientCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(default="Бизнес", max_length=120)
    city: str = Field(default="Москва", max_length=80)
    source: str = Field(default="Добавлен вручную", max_length=80)
    phone: str = Field(default="", max_length=80)
    website: str = Field(default="", max_length=300)


@app.post("/api/clients")
def create_client(request: ClientCreateRequest) -> dict[str, Any]:
    result = insert_clients([_enrich({
        "name": request.name,
        "niche": request.category,
        "city": request.city,
        "source": request.source,
        "phone": request.phone,
        "website": request.website,
        "address": "",
        "card_url": "",
        "social_url": "",
    })])
    # Берём идентификатор, который вернул insert_clients: поиск по имени промахивался
    # на пробелах и мог отдать чужую запись, слитую по телефону или домену.
    outcome = (result.get("results") or [{}])[0]
    client_id = outcome.get("client_id")
    if client_id is None:
        raise HTTPException(status_code=500, detail="Не удалось сохранить клиента")
    stored = next((client for client in result["clients"] if client["id"] == client_id), None)
    if stored is None:
        raise HTTPException(status_code=500, detail="Клиент сохранён, но недоступен в списке")
    return {**stored, "outcome": outcome.get("outcome", "inserted")}


@app.get("/api/parser/settings")
def parser_settings() -> dict[str, Any]:
    return get_parser_settings()


class ParserSettingsRequest(BaseModel):
    city: str = Field(min_length=2, max_length=80)
    niches: list[str] = Field(min_length=1, max_length=20)
    sources: list[str] = Field(min_length=1, max_length=4)
    limit: int = Field(default=10, ge=1, le=50)
    start_page: int = Field(default=1, ge=1, le=999)


@app.put("/api/parser/settings")
def update_parser_settings(request: ParserSettingsRequest) -> dict[str, Any]:
    allowed_sources = {"2gis", "yandex"}
    if any(source.lower() not in allowed_sources for source in request.sources):
        raise HTTPException(status_code=422, detail="Поддерживаются источники 2GIS и Яндекс Карты")
    try:
        return save_parser_settings(request.city, request.niches, request.sources, request.limit, request.start_page)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/parser/runs")
def parser_runs(limit: int = 20) -> dict[str, Any]:
    return {"runs": list_parser_runs(limit)}


@app.get("/api/parser/runs/{run_id}")
def parser_run_detail(run_id: str) -> dict[str, Any]:
    run = get_parser_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Запуск парсера не найден")
    return run


class ClientStatusRequest(BaseModel):
    status: str = Field(min_length=2, max_length=30)
    next_step: str = Field(default="", max_length=160)


@app.put("/api/clients/{client_id}/status")
def change_client_status(client_id: int, request: ClientStatusRequest) -> dict[str, Any]:
    allowed_statuses = {"Новый", "Написал", "Ответили", "Созвон", "КП", "Закрыто", "Отказ"}
    if request.status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Неизвестный статус клиента")
    next_step = request.next_step or {
        "Новый": "Написать владельцу",
        "Написал": "Жду ответа",
        "Ответили": "Подготовить КП",
        "Созвон": "Назначить созвон",
        "КП": "Отправить предложение",
        "Закрыто": "Запустить проект",
        "Отказ": "Вернуться позже",
    }[request.status]
    client = update_client_status(client_id, request.status, next_step)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return client


@app.delete("/api/clients/{client_id}")
def remove_client(client_id: int) -> dict[str, Any]:
    if not archive_client(client_id):
        raise HTTPException(status_code=404, detail="Клиент не найден или уже скрыт")
    return {"ok": True, "archived_id": client_id}


@app.delete("/api/clients")
def clear_clients() -> dict[str, Any]:
    archived_count = archive_all_clients()
    return {"ok": True, "archived_count": archived_count}


@app.post("/api/clients/restore-all")
def restore_all_archived_clients() -> dict[str, Any]:
    restored_count = restore_all_clients()
    return {"ok": True, "restored_count": restored_count}


@app.post("/api/clients/{client_id}/restore")
def restore_archived_client(client_id: int) -> dict[str, Any]:
    client = restore_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Скрытый клиент не найден")
    return client


@app.post("/api/clients/parse")
def start_parse(request: ParseRequest) -> dict[str, str]:
    niches = request.normalized_niches()
    sources = request.normalized_sources()
    if not niches:
        return {"job_id": "", "error": "Добавьте хотя бы одну нишу в настройках парсера"}
    if not sources or any(source not in {"2gis", "yandex"} for source in sources):
        return {"job_id": "", "error": "Выберите 2GIS или Яндекс Карты в настройках парсера"}
    with jobs_lock:
        # Два одновременных парсинга открыли бы два окна Chrome на 2GIS — это прямой
        # путь к CAPTCHA и к конкуренции за блокировку записи в SQLite.
        if any(active.status in {"pending", "running"} for active in jobs.values()):
            return {"job_id": "", "error": "Парсер уже работает. Дождитесь окончания текущего запуска."}
        job = ParserJob(id=uuid.uuid4().hex, city=request.city.strip(), niches=niches, sources=sources, limit=request.limit, start_page=request.start_page)
        jobs[job.id] = job
        for stale_id in list(jobs)[:-PARSE_JOB_HISTORY_LIMIT]:
            jobs.pop(stale_id, None)
    create_parser_run(job.id, job.city, ", ".join(niches), ", ".join(sources), request.limit, request.start_page)
    threading.Thread(target=_run_job, args=(job,), daemon=True, name=f"semix-parser-{job.id[:8]}").start()
    return {"job_id": job.id}


@app.get("/api/clients/jobs/{job_id}")
def parse_status(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "missing", "message": "Задача не найдена", "clients": []}
    return job.snapshot()


def _run_job(job: ParserJob) -> None:
    job.status = "running"
    job.message = "Запускаю парсер клиентов"
    try:
        leads: list[dict[str, Any]] = []
        for niche in job.niches:
            job.message = f"Парсю нишу: {niche}"
            leads.extend(collect_leads(job.city, niche, job.sources, job.limit, on_status=lambda value: setattr(job, "message", value), start_page=job.start_page))
        if not leads:
            raise RuntimeError("Источники не вернули карточки. Проверьте город/нишу или повторите позже: источник мог показать CAPTCHA.")
        enriched = [_enrich(lead) for lead in leads]
        stored = insert_clients(enriched)
        save_parser_run_results(job.id, stored["results"])
        job.clients = [item["snapshot"] for item in stored["results"]]
        job.count = int(stored["inserted_count"])
        job.skipped_count = int(stored["duplicate_count"])
        job.status = "done"
        page_note = f", страница 2GIS — {job.start_page}" if job.start_page > 1 else ""
        restored = int(stored.get("restored_count") or 0)
        restored_note = f", вернулось из архива — {restored}" if restored else ""
        job.message = f"Готово: новых — {job.count}, уже были в базе — {job.skipped_count}{restored_note}{page_note}"
        update_parser_run(job.id, job.status, job.count, job.message, skipped_count=job.skipped_count, parsed_count=len(stored["results"]))
    except Exception as error:  # noqa: BLE001 - surface parser errors in the job UI
        job.status = "error"
        job.error = str(error)
        job.message = "Парсер завершился с ошибкой"
        update_parser_run(job.id, job.status, job.count, job.message, job.error, job.skipped_count, len(job.clients))


def _enrich(lead: dict[str, Any]) -> dict[str, Any]:
    """Добавляет боль и теги. Скоринг и контакты считает insert_clients — единственный владелец."""

    website = str(lead.get("website") or "").strip()
    phone = str(lead.get("phone") or "").strip()
    niche = str(lead.get("niche") or "Бизнес")
    normalized = {**lead, "website": website, "phone": phone, "niche": niche}
    contacts = contacts_from_lead(normalized)
    direct = {item["type"] for item in contacts if item["type"] in {"telegram", "whatsapp", "email"}}
    has_real_website = is_real_website(website)
    pain = "Нет сайта — часть заявок уходит к конкурентам." if not has_real_website else "Можно усилить онлайн-заявки и автоматизацию."
    if direct and not has_real_website:
        pain = "Есть канал для контакта, но нет сайта — хороший кандидат для первого сообщения."
    tags = ["Сайт" if not has_real_website else "Аудит сайта", "CRM", "Автоматизация"]
    if phone:
        tags.append("Телефон")
    if direct:
        tags.extend(sorted({"telegram": "Telegram", "whatsapp": "WhatsApp", "email": "E-mail"}[item] for item in direct))
    return {
        **normalized,
        "pain": pain,
        "contacts": contacts,
        "tags": list(dict.fromkeys(tags)),
        "niche": niche,
    }


# --------------------------------------------------------------------------------------
# Мои проекты: карточки локальных проектов и запуск их дев-серверов
# --------------------------------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    path: str = Field(default="", max_length=500)
    command: str = Field(default="", max_length=400)
    url: str = Field(default="", max_length=300)
    port: int | None = Field(default=None, ge=1, le=65535)
    tags: list[str] = Field(default_factory=list, max_length=12)
    category: str = Field(default="Веб-приложение", max_length=40)
    status: str = Field(default="В работе", max_length=20)
    version: str = Field(default="", max_length=30)
    repo_url: str = Field(default="", max_length=300)
    progress: int = Field(default=0, ge=0, le=100)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    path: str | None = Field(default=None, max_length=500)
    command: str | None = Field(default=None, max_length=400)
    url: str | None = Field(default=None, max_length=300)
    port: int | None = Field(default=None, ge=1, le=65535)
    tags: list[str] | None = Field(default=None, max_length=12)
    category: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=20)
    version: str | None = Field(default=None, max_length=30)
    repo_url: str | None = Field(default=None, max_length=300)
    progress: int | None = Field(default=None, ge=0, le=100)
    archived: bool | None = None


class ProjectDetectRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)


def _require_project(project_id: int) -> dict[str, Any]:
    project = projects_storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project


@app.get("/api/projects")
def projects(archived: bool = Query(default=False)) -> dict[str, Any]:
    items = projects_storage.list_projects(include_archived=archived)
    return {
        "projects": items,
        "stats": projects_storage.project_stats(),
        "runtime": project_runner.statuses(items),
        "categories": list(PROJECT_CATEGORIES),
        "statuses": list(PROJECT_STATUSES),
    }


@app.post("/api/projects", status_code=201)
def add_project(request: ProjectCreateRequest) -> dict[str, Any]:
    try:
        project = Project(
            name=request.name, description=request.description, path=request.path, command=request.command,
            url=request.url, port=request.port, tags=tuple(request.tags), category=request.category,
            status=request.status, version=request.version, repo_url=request.repo_url, progress=request.progress,
        )
        return projects_storage.create_project(project, tags=request.tags)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.put("/api/projects/{project_id}")
def edit_project(project_id: int, request: ProjectUpdateRequest) -> dict[str, Any]:
    try:
        project = projects_storage.update_project(
            project_id,
            tags=request.tags,
            name=request.name, description=request.description, path=request.path, command=request.command,
            url=request.url, port=request.port, category=request.category, status=request.status,
            version=request.version, repo_url=request.repo_url, progress=request.progress, archived=request.archived,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if project is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project


@app.delete("/api/projects/{project_id}")
def remove_project(project_id: int) -> dict[str, Any]:
    _require_project(project_id)
    # Удаляем карточку только после остановки процесса, иначе он остался бы без владельца.
    project_runner.stop(project_id)
    if not projects_storage.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Проект не найден")
    return {"ok": True, "deleted_id": project_id}


@app.post("/api/projects/detect")
def detect_project_folder(request: ProjectDetectRequest) -> dict[str, Any]:
    return detect_project(request.path).as_dict()


@app.post("/api/projects/start-all", dependencies=[Depends(guard_powerful_action)])
def start_all_projects() -> dict[str, Any]:
    """Поднимает все проекты, у которых задана команда запуска."""

    started: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for project in projects_storage.list_projects():
        name = project["name"]
        if not project["command"]:
            skipped.append({"id": project["id"], "name": name, "reason": "не задана команда запуска"})
            continue
        if project_runner.is_running(project["id"]):
            skipped.append({"id": project["id"], "name": name, "reason": "уже запущен"})
            continue
        try:
            runtime = project_runner.start(project)
        except ValueError as error:
            failed.append({"id": project["id"], "name": name, "error": str(error)})
            continue
        projects_storage.mark_project_started(project["id"])
        started.append({"id": project["id"], "name": name, "port": runtime.get("port")})
    return {"started": started, "skipped": skipped, "failed": failed}


@app.post("/api/projects/stop-all", dependencies=[Depends(guard_powerful_action)])
def stop_all_projects() -> dict[str, Any]:
    return {"stopped_count": project_runner.stop_all()}


@app.post("/api/projects/{project_id}/start", dependencies=[Depends(guard_powerful_action)])
def start_project(project_id: int) -> dict[str, Any]:
    project = _require_project(project_id)
    try:
        runtime = project_runner.start(project)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    projects_storage.mark_project_started(project_id)
    return {"ok": True, "runtime": runtime, "project": projects_storage.get_project(project_id)}


@app.post("/api/projects/{project_id}/stop", dependencies=[Depends(guard_powerful_action)])
def stop_project(project_id: int) -> dict[str, Any]:
    _require_project(project_id)
    return {"ok": True, "runtime": project_runner.stop(project_id)}


@app.get("/api/projects/{project_id}/logs")
def project_logs(project_id: int, limit: int = Query(default=200, ge=1, le=400)) -> dict[str, Any]:
    project = _require_project(project_id)
    return {
        "project_id": project_id,
        "runtime": project_runner.status(project),
        "logs": project_runner.logs(project_id, limit),
    }


# --------------------------------------------------------------------------------------
# Работа (вакансии): ручной трекер откликов и сбор вакансий из внешних источников
# --------------------------------------------------------------------------------------


class JobCreateRequest(BaseModel):
    company: str = Field(default="", max_length=200)
    role: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=5000)
    url: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_text: str = Field(default="", max_length=120)
    location: str = Field(default="", max_length=160)
    employment: str = Field(default="", max_length=120)
    source: str = Field(default="manual", max_length=40)


class JobUpdateRequest(BaseModel):
    status: str | None = Field(default=None, max_length=30)
    next_step: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=2000)
    archived: bool | None = None


class JobSettingsRequest(BaseModel):
    sources: list[str] = Field(min_length=1, max_length=len(JOB_SOURCES))
    keywords: list[str] = Field(default_factory=list, max_length=40)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=40)
    telegram_channels: list[str] = Field(default_factory=list, max_length=60)
    area: str = Field(default="Россия", max_length=80)
    salary_min: int = Field(default=0, ge=0, le=100000000)
    remote_only: bool = False
    per_source_limit: int = Field(default=50, ge=1, le=100)


@app.get("/api/jobs")
def jobs_list(
    query: str = Query(default="", max_length=120),
    source: str = Query(default="", max_length=40),
    status: str = Query(default="", max_length=30),
    min_salary: int | None = Query(default=None, ge=0),
    sort: str = Query(default="relevance", max_length=20),
    archived: bool = Query(default=False),
) -> dict[str, Any]:
    filters = jobs_storage.JobFilters(
        query=query, source=source, status=status, min_salary=min_salary, sort=sort, include_archived=archived
    )
    return {
        "jobs": jobs_storage.list_jobs(filters),
        "stats": jobs_storage.job_stats(),
        "sources": jobs_storage.list_job_source_statuses(),
        "statuses": list(JOB_STATUSES),
        "available": list(JOB_SOURCES),
    }


@app.post("/api/jobs", status_code=201)
def add_job(request: JobCreateRequest) -> dict[str, Any]:
    try:
        vacancy = JobVacancy(
            source=request.source or "manual", external_id="", company=request.company, role=request.role,
            description=request.description, url=request.url, tags=tuple(request.tags),
            salary_min=request.salary_min, salary_max=request.salary_max, salary_text=request.salary_text,
            location=request.location, employment=request.employment,
        )
        settings = job_settings_from_dict(jobs_storage.get_job_settings())
        score, reasons, match = score_vacancy(vacancy, settings)
        stored, _ = jobs_storage.create_job(vacancy, score, reasons, match)
        return stored
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/jobs/settings")
def job_settings() -> dict[str, Any]:
    return jobs_storage.get_job_settings()


@app.put("/api/jobs/settings")
def update_job_settings(request: JobSettingsRequest) -> dict[str, Any]:
    if any(source not in JOB_SOURCES for source in request.sources):
        raise HTTPException(status_code=422, detail="Неизвестный источник вакансий")
    try:
        return jobs_storage.save_job_settings(JobSettings(
            sources=tuple(request.sources), keywords=tuple(request.keywords),
            excluded_keywords=tuple(request.excluded_keywords), telegram_channels=tuple(request.telegram_channels),
            area=request.area, salary_min=request.salary_min, remote_only=request.remote_only,
            per_source_limit=request.per_source_limit,
        ))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/jobs/runs")
def job_runs_list(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    return {"runs": jobs_storage.list_job_runs(limit)}


@app.post("/api/jobs/parse", dependencies=[Depends(guard_powerful_action)])
def start_job_parse() -> dict[str, Any]:
    settings = job_settings_from_dict(jobs_storage.get_job_settings())
    if not settings.sources:
        return {"run_id": "", "error": "Выберите хотя бы один источник вакансий"}
    if job_collector.is_busy():
        return {"run_id": "", "error": "Сбор вакансий уже идёт"}
    run = JobParseRun(id=uuid.uuid4().hex, sources=list(settings.sources))
    with job_runs_lock:
        job_runs[run.id] = run
        for stale_id in list(job_runs)[:-PARSE_JOB_HISTORY_LIMIT]:
            job_runs.pop(stale_id, None)
    threading.Thread(
        target=_run_job_parse, args=(run, settings), daemon=True, name=f"semix-jobs-{run.id[:8]}"
    ).start()
    return {"run_id": run.id}


@app.get("/api/jobs/parse/{run_id}")
def job_parse_status(run_id: str) -> dict[str, Any]:
    with job_runs_lock:
        run = job_runs.get(run_id)
    if run is None:
        return {"run_id": run_id, "status": "missing", "message": "Запуск не найден", "sources": {}}
    return run.snapshot()


# Маршруты с параметром объявлены последними: иначе «settings», «runs» и «parse»
# попадали бы в {job_id} и падали с 422 при разборе числа.
@app.put("/api/jobs/{job_id}")
def edit_job(job_id: int, request: JobUpdateRequest) -> dict[str, Any]:
    try:
        job = jobs_storage.update_job(job_id, request.status, request.next_step, request.note, request.archived)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if job is None:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    return job


@app.delete("/api/jobs/{job_id}")
def remove_job(job_id: int) -> dict[str, Any]:
    if not jobs_storage.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    return {"ok": True, "deleted_id": job_id}


def _run_job_parse(run: JobParseRun, settings: JobSettings) -> None:
    try:
        job_collector.collect(run, settings)
    except RuntimeError as error:
        run.status = "error"
        run.error = str(error)
        run.message = "Сбор вакансий уже идёт"
    except Exception as error:  # noqa: BLE001 - показываем сбой в интерфейсе, а не роняем поток
        logger.exception("Сбор вакансий завершился ошибкой")
        run.status = "error"
        run.error = str(error)[:400]
        run.message = "Сбор вакансий завершился с ошибкой"


# --------------------------------------------------------------------------------------
# AI: разбор клиента и первое сообщение
# --------------------------------------------------------------------------------------


class AiProfileRequest(BaseModel):
    name: str = Field(default="", max_length=80)
    role: str = Field(default="", max_length=300)
    stack: str = Field(default="", max_length=300)
    portfolio_url: str = Field(default="", max_length=300)
    price_from: str = Field(default="", max_length=160)
    cases: str = Field(default="", max_length=500)
    offer: str = Field(default="", max_length=300)
    tone: str = Field(default="", max_length=200)
    signature: str = Field(default="", max_length=80)


class AiSettingsRequest(BaseModel):
    api_key: str | None = Field(default=None, max_length=500)
    model: str = Field(min_length=1, max_length=100)
    timeout: float = Field(ge=5, le=300)


class AiSettingsTestRequest(BaseModel):
    api_key: str | None = Field(default=None, max_length=500)
    model: str = Field(min_length=1, max_length=100)
    timeout: float = Field(ge=5, le=300)


@app.get("/api/ai/settings")
def ai_settings() -> dict[str, Any]:
    return get_safe_ai_settings()


@app.put("/api/ai/settings", dependencies=[Depends(guard_powerful_action)])
def update_ai_settings(request: AiSettingsRequest) -> dict[str, Any]:
    try:
        return save_ai_settings(
            api_key=request.api_key,
            model=request.model,
            timeout=request.timeout,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/ai/settings/key", dependencies=[Depends(guard_powerful_action)])
def delete_ai_settings_key() -> dict[str, Any]:
    removed = remove_ai_settings_key()
    return {"ok": True, "removed": removed, "settings": get_safe_ai_settings()}


@app.post("/api/ai/settings/test", dependencies=[Depends(guard_powerful_action)])
def test_ai_settings(request: AiSettingsTestRequest) -> dict[str, Any]:
    effective = resolve_ai_settings()
    key = request.api_key.strip() if request.api_key is not None else str(effective["api_key"])
    if not key:
        raise HTTPException(status_code=400, detail="Сначала укажите API-ключ OpenCode Go")
    try:
        model, timeout = validate_settings_values(request.model, request.timeout)
        client = AiClient(AiSettings(
            api_key=key,
            base_url=OPENCODE_GO_BASE_URL,
            model=model,
            timeout=timeout,
        ))
        client.complete(
            "Ты проверяешь подключение к OpenCode Go.",
            "Ответь одним словом: OK",
            temperature=0,
            max_tokens=8,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AiDisabledError as error:
        raise HTTPException(status_code=400, detail="Сначала укажите API-ключ OpenCode Go") from error
    except AiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"ok": True, "message": "Подключение работает", "model": model}


@app.get("/api/ai/status")
def ai_status() -> dict[str, Any]:
    """Включён ли AI. Фронтенд по этому ответу прячет или показывает кнопки."""

    settings = get_safe_ai_settings()
    return {
        "enabled": settings["enabled"],
        "model": settings["model"] if settings["enabled"] else "",
        "base_url": settings["base_url"],
        "hint": "" if settings["enabled"] else "Добавьте ключ OpenCode Go в разделе «Настройки»",
    }


@app.get("/api/ai/profile")
def ai_profile() -> dict[str, Any]:
    return get_ai_profile().as_dict()


@app.put("/api/ai/profile")
def update_ai_profile(request: AiProfileRequest) -> dict[str, Any]:
    current = get_ai_profile()
    # Пустые поля оставляют текущее значение: форма не должна затирать профиль пробелами.
    merged = {key: (value.strip() or getattr(current, key)) for key, value in request.model_dump().items()}
    return save_ai_profile(ExecutorProfile(**merged)).as_dict()


@app.get("/api/ai/clients/{client_id}/message")
def ai_client_message_cached(client_id: int) -> dict[str, Any]:
    """Ранее сгенерированный разбор, если он есть. Ничего не запрашивает у модели."""

    client = next((item for item in list_clients() if item["id"] == client_id), None)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    stored = get_cached_ai_result("client_message", "client", client_id, ai_input_hash(
        build_ai_input(client, get_ai_profile())
    ))
    if stored is None:
        return {"ready": False}
    first = stored["variants"][0]["text"] if stored.get("variants") else ""
    return {"ready": True, **stored, "links": ai_channel_links(client, first)}


@app.post("/api/ai/clients/{client_id}/message", dependencies=[Depends(guard_powerful_action)])
def ai_client_message(client_id: int, force: bool = Query(default=False)) -> dict[str, Any]:
    client = next((item for item in list_clients() if item["id"] == client_id), None)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    try:
        # Генерация занимает секунды, поэтому идёт синхронно: отдельная очередь
        # ради одного клиента усложнила бы код без выигрыша.
        return {"ready": True, **generate_client_message(client, force=force)}
    except AiDisabledError as error:
        raise HTTPException(status_code=503, detail="AI выключен: не задан OPENCODE_API_KEY") from error
    except AiError as error:
        logger.warning("Генерация сообщения для клиента %s не удалась: %s", client_id, error)
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.delete("/api/ai/clients/{client_id}/message", dependencies=[Depends(guard_powerful_action)])
def ai_client_message_forget(client_id: int) -> dict[str, Any]:
    return {"ok": True, "removed": forget_ai_result("client_message", "client", client_id)}
