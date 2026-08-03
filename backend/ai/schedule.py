from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from .client import AiClient, AiDisabledError, AiError


INTENSITY_LIMITS = {
    "light": 7,
    "balanced": 12,
    "intensive": 16,
}

INTENSITY_LABELS = {
    "light": "лёгкая: 1 основной блок в рабочий день, оставляй запас",
    "balanced": "сбалансированная: 1–2 блока в рабочий день",
    "intensive": "интенсивная: до 3 блоков в день, но без нереалистичной перегрузки",
}

TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
ALLOWED_KINDS = {"task", "meeting"}

SYSTEM_PROMPT = """Ты — практичный ассистент по недельному планированию внутри CRM.
Составь реалистичный план, который помогает достичь указанного результата недели.

Правила:
- верни только JSON-объект без markdown и пояснений вокруг него;
- не удаляй, не повторяй и не переноси существующие задачи;
- учитывай незавершённые цели и уже занятые временные слоты;
- каждая задача должна начинаться с конкретного действия и иметь понятный результат;
- не придумывай встречи и обязательства, которых нет во входных данных;
- распределяй сложную работу на первую половину недели, а проверку и завершение — ближе к концу;
- оставляй разумный запас, не заполняй каждый час;
- используй kind="meeting" только для явно указанного созвона или встречи, иначе kind="task";
- time оставляй пустым, если точное время не нужно.

Строгая JSON-схема:
{
  "focus": "короткий фокус недели до 160 символов",
  "summary": "объяснение логики плана до 600 символов",
  "tasks": [
    {
      "date": "YYYY-MM-DD",
      "time": "HH:MM или пустая строка",
      "title": "конкретная задача до 160 символов",
      "kind": "task или meeting",
      "reason": "зачем эта задача нужна, до 240 символов"
    }
  ]
}
"""


def _parse_date(value: Any, label: str) -> date:
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError as error:
        raise AiError(f"{label} должна быть датой в формате YYYY-MM-DD") from error


def _clean_text(value: Any, *, label: str, minimum: int, maximum: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) < minimum:
        raise AiError(f"{label} слишком короткий")
    if len(text) > maximum:
        raise AiError(f"{label} длиннее {maximum} символов")
    return text


def _normalize_task(
    raw: Any,
    *,
    week_start: date,
    week_end: date,
    include_weekend: bool,
    today: date,
) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise AiError("Каждая задача должна быть JSON-объектом")

    task_date = _parse_date(raw.get("date"), "Дата задачи")
    if not week_start <= task_date <= week_end:
        raise AiError("Дата задачи находится вне выбранной недели")
    if week_start <= today <= week_end and task_date < today:
        raise AiError("Нельзя планировать задачу на уже прошедший день текущей недели")
    if not include_weekend and task_date.weekday() >= 5:
        raise AiError("План содержит задачу на выходной, хотя выходные отключены")

    task_time = str(raw.get("time") or "").strip()
    if task_time and not TIME_PATTERN.fullmatch(task_time):
        raise AiError("У задачи указано некорректное время")

    kind = str(raw.get("kind") or "task").strip().casefold()
    if kind not in ALLOWED_KINDS:
        raise AiError("Модель вернула неподдерживаемый тип задачи")

    return {
        "date": task_date.isoformat(),
        "time": task_time,
        "title": _clean_text(raw.get("title"), label="Название задачи", minimum=3, maximum=160),
        "kind": kind,
        "reason": _clean_text(raw.get("reason"), label="Объяснение задачи", minimum=3, maximum=240),
    }


def _validate_payload(
    payload: dict[str, Any],
    *,
    week_start: date,
    week_end: date,
    include_weekend: bool,
    today: date,
    existing_keys: set[tuple[str, str]],
    intensity: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AiError("План должен быть JSON-объектом")

    focus = _clean_text(payload.get("focus"), label="Фокус недели", minimum=3, maximum=160)
    summary = _clean_text(payload.get("summary"), label="Описание плана", minimum=3, maximum=600)
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise AiError("План должен содержать хотя бы одну задачу")
    if len(raw_tasks) > 20:
        raise AiError("План должен содержать не более 20 задач")

    normalized: list[tuple[int, dict[str, str]]] = []
    seen = set(existing_keys)
    for index, raw_task in enumerate(raw_tasks):
        task = _normalize_task(
            raw_task,
            week_start=week_start,
            week_end=week_end,
            include_weekend=include_weekend,
            today=today,
        )
        key = (task["date"], task["title"].casefold())
        if key in seen:
            continue
        seen.add(key)
        normalized.append((index, task))

    if not normalized:
        raise AiError("План не содержит новых задач: все предложения уже есть в расписании")
    if len(normalized) > INTENSITY_LIMITS[intensity]:
        raise AiError(
            f"Для выбранной нагрузки модель должна вернуть не более {INTENSITY_LIMITS[intensity]} задач"
        )

    normalized.sort(key=lambda item: (item[1]["date"], item[1]["time"] or "99:99", item[0]))
    tasks = [{"id": f"ai-{index}", **task} for index, (_, task) in enumerate(normalized, start=1)]
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "focus": focus,
        "summary": summary,
        "tasks": tasks,
    }


def _prompt_schedule_context(schedule: dict[str, Any]) -> dict[str, Any]:
    tasks = []
    for task in schedule.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        tasks.append({
            "date": task.get("date"),
            "time": task.get("time") or "",
            "title": task.get("title"),
            "kind": task.get("kind") or "task",
            "done": bool(task.get("done")),
        })
    goals = []
    for goal in schedule.get("goals") or []:
        if isinstance(goal, dict) and not goal.get("done") and str(goal.get("title") or "").strip():
            goals.append({"title": str(goal["title"]).strip()})
    return {
        "existing_tasks": tasks,
        "unfinished_goals": goals,
        "current_summary": str(schedule.get("summary") or "").strip(),
    }


def generate_week_plan(
    *,
    week_start: str,
    objective: str,
    intensity: str,
    include_weekend: bool,
    schedule: dict[str, Any],
    ai_client: AiClient | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    selected = _parse_date(week_start, "Начало недели")
    selected -= timedelta(days=selected.weekday())
    week_end = selected + timedelta(days=6)
    current_day = today or date.today()
    if week_end < current_day:
        raise ValueError("Нельзя составить новый план для полностью прошедшей недели")

    clean_objective = re.sub(r"\s+", " ", objective or "").strip()
    if len(clean_objective) < 3:
        raise ValueError("Опишите главный результат недели")
    if len(clean_objective) > 1200:
        raise ValueError("Главный результат недели длиннее 1200 символов")
    normalized_intensity = str(intensity or "").strip().casefold()
    if normalized_intensity not in INTENSITY_LIMITS:
        raise ValueError("Неизвестная нагрузка недели")

    context = _prompt_schedule_context(schedule)
    existing_keys = {
        (str(task.get("date") or ""), str(task.get("title") or "").strip().casefold())
        for task in context["existing_tasks"]
        if str(task.get("date") or "") and str(task.get("title") or "").strip()
    }
    available_dates = [
        (selected + timedelta(days=offset)).isoformat()
        for offset in range(7)
        if (include_weekend or offset < 5)
        and not (selected <= current_day <= week_end and selected + timedelta(days=offset) < current_day)
    ]
    if not available_dates:
        raise ValueError("В выбранной неделе не осталось доступных дней для планирования")

    user_prompt = (
        f"Сегодня: {current_day.isoformat()}\n"
        f"Выбранная неделя: {selected.isoformat()} — {week_end.isoformat()}\n"
        f"Доступные даты для новых задач: {', '.join(available_dates)}\n"
        f"Главный результат недели: {clean_objective}\n"
        f"Нагрузка: {INTENSITY_LABELS[normalized_intensity]}; максимум "
        f"{INTENSITY_LIMITS[normalized_intensity]} новых задач.\n"
        f"Учитывать выходные: {'да' if include_weekend else 'нет'}\n\n"
        "Текущее расписание и цели (доверенные данные CRM):\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        "Составь выполнимый черновик только из новых задач."
    )

    engine = ai_client or AiClient()
    if not engine.enabled:
        raise AiDisabledError("Не задан OPENCODE_API_KEY")

    validator = lambda payload: _validate_payload(
        payload,
        week_start=selected,
        week_end=week_end,
        include_weekend=include_weekend,
        today=current_day,
        existing_keys=existing_keys,
        intensity=normalized_intensity,
    )
    payload = engine.complete_json(
        SYSTEM_PROMPT,
        user_prompt,
        temperature=0.35,
        max_tokens=2600,
        validate=validator,
    )
    return validator(payload)
