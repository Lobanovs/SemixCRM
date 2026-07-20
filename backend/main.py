from __future__ import annotations

import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException
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
)
from .parser import collect_leads
from .lead_utils import calculate_lead_score, contacts_from_lead, is_real_website


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Semix CRM API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
jobs: dict[str, ParserJob] = {}
jobs_lock = threading.Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "semix-crm"}


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
    match = next((client for client in result["clients"] if client["name"] == request.name and client["city"] == request.city), None)
    if match is None:
        raise HTTPException(status_code=500, detail="Не удалось сохранить клиента")
    return match


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
    job = ParserJob(id=uuid.uuid4().hex, city=request.city.strip(), niches=niches, sources=sources, limit=request.limit, start_page=request.start_page)
    create_parser_run(job.id, job.city, ", ".join(niches), ", ".join(sources), request.limit, request.start_page)
    with jobs_lock:
        jobs[job.id] = job
    threading.Thread(target=_run_job, args=(job, request), daemon=True, name=f"semix-parser-{job.id[:8]}").start()
    return {"job_id": job.id}


@app.get("/api/clients/jobs/{job_id}")
def parse_status(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "missing", "message": "Задача не найдена", "clients": []}
    return job.snapshot()


def _run_job(job: ParserJob, request: ParseRequest) -> None:
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
        job.message = f"Готово: новых — {job.count}, уже были в базе — {job.skipped_count}{page_note}"
        update_parser_run(job.id, job.status, job.count, job.message, skipped_count=job.skipped_count, parsed_count=len(stored["results"]))
    except Exception as error:  # noqa: BLE001 - surface parser errors in the job UI
        job.status = "error"
        job.error = str(error)
        job.message = "Парсер завершился с ошибкой"
        update_parser_run(job.id, job.status, job.count, job.message, job.error, job.skipped_count, len(job.clients))


def _enrich(lead: dict[str, Any]) -> dict[str, Any]:
    website = str(lead.get("website") or "").strip()
    phone = str(lead.get("phone") or "").strip()
    niche = str(lead.get("niche") or "Бизнес")
    normalized = {**lead, "website": website, "phone": phone, "niche": niche}
    score, reasons, match_score = calculate_lead_score(normalized)
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
        "match_score": match_score,
        "lead_score": score,
        "lead_score_reasons": reasons,
        "contacts": contacts,
        "tags": list(dict.fromkeys(tags)),
        "niche": niche,
    }
