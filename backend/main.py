from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import init_db, insert_clients, list_clients
from .parser import collect_2gis


class ParseRequest(BaseModel):
    city: str = Field(default="Москва", min_length=2, max_length=80)
    niche: str = Field(default="салоны красоты", min_length=2, max_length=120)
    source: str = Field(default="2gis", max_length=20)
    limit: int = Field(default=10, ge=1, le=50)


@dataclass
class ParserJob:
    id: str
    status: str = "pending"
    message: str = "Подготовка парсера"
    error: str = ""
    count: int = 0
    clients: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {"job_id": self.id, "status": self.status, "message": self.message, "error": self.error, "count": self.count, "clients": self.clients}


app = FastAPI(title="Semix CRM API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
jobs: dict[str, ParserJob] = {}
jobs_lock = threading.Lock()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "semix-crm"}


@app.get("/api/clients")
def clients() -> dict[str, Any]:
    return {"clients": list_clients()}


@app.post("/api/clients/parse")
def start_parse(request: ParseRequest) -> dict[str, str]:
    if request.source.lower() != "2gis":
        return {"job_id": "", "error": "Пока подключён парсер 2GIS; остальные источники добавим следующим этапом."}
    job = ParserJob(id=uuid.uuid4().hex)
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
        leads = collect_2gis(request.city, request.niche, request.limit, on_status=lambda value: setattr(job, "message", value))
        if not leads:
            raise RuntimeError("2GIS не вернул карточки. Проверьте город/нишу или повторите позже: источник мог показать CAPTCHA.")
        enriched = [_enrich(lead) for lead in leads]
        job.clients = insert_clients(enriched)
        job.count = len(leads)
        job.status = "done"
        job.message = f"Готово: добавлено или обновлено клиентов — {len(leads)}"
    except Exception as error:  # noqa: BLE001 - surface parser errors in the job UI
        job.status = "error"
        job.error = str(error)
        job.message = "Парсер завершился с ошибкой"


def _enrich(lead: dict[str, Any]) -> dict[str, Any]:
    website = str(lead.get("website") or "").strip()
    phone = str(lead.get("phone") or "").strip()
    reviews = int(lead.get("reviews") or 0)
    score = 70 + (10 if not website else 0) + (5 if phone else 0) + (5 if reviews >= 50 else 0)
    niche = str(lead.get("niche") or "Бизнес")
    pain = "Нет сайта — часть заявок уходит к конкурентам." if not website else "Можно усилить онлайн-заявки и автоматизацию."
    tags = ["Сайт" if not website else "Аудит сайта", "CRM", "Автоматизация"]
    if phone:
        tags.append("Телефон")
    return {**lead, "pain": pain, "match_score": min(score, 98), "tags": tags, "niche": niche}
