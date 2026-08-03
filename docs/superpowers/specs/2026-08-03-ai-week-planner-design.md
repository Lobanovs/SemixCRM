# AI Week Planner Design

## Goal

Add an OpenCode Go assistant to «Расписание по дням» that turns the user's weekly objective into a practical draft, lets the user review it, and only then adds selected tasks to the schedule.

## Decision

Use a two-step planner modal: **brief → review → apply**.

Alternatives considered:

1. Directly write model output into the schedule. This is fast but can overwrite intent, create poor tasks, or add unwanted work.
2. Show a chat-style text answer. This is simple but forces the user to manually recreate every task.
3. Generate a structured draft with confirmation. This gives useful automation while keeping the user in control. This is the selected approach.

The prior project instruction to proceed without clarification is treated as approval of this conservative, reversible design.

## User experience

The Schedule toolbar gets a visually distinct `Составить неделю с ИИ` button with a Lucide sparkle icon. It opens a desktop-focused modal that uses the existing Semix light and premium-black visual systems.

Step 1 asks for:

- the main outcome or work that must be completed this week;
- workload: light, balanced, or intensive;
- whether the model may use Saturday and Sunday.

The objective is prefilled from unfinished weekly goals when available, but remains editable. The form has visible labels, an explicit AI label, progress feedback, and an error recovery action.

Step 2 shows:

- a short suggested focus for the week;
- an AI summary explaining the planning logic;
- tasks grouped by day, with time, task/meeting type, and a short reason;
- a checkbox for every task;
- `Сгенерировать заново`, `Назад`, and `Добавить N задач` actions.

No task is persisted during generation. Applying the draft adds only checked tasks. Exact duplicates already saved for the same date are skipped. After success the schedule reloads and shows how many tasks were added and skipped.

## Backend architecture

Create `backend/ai/schedule.py` as the isolated planning service. It receives trusted schedule context, calls the existing `AiClient.complete_json`, validates the model response, and returns a normalized plan.

The prompt includes:

- exact week dates and today's date;
- user objective and chosen workload;
- existing schedule tasks and unfinished goals;
- whether weekends are allowed;
- a strict JSON schema and planning rules.

Validation rejects:

- dates outside the requested week;
- past days when planning the current week;
- weekend tasks when weekends are disabled;
- invalid times or task kinds;
- vague, empty, duplicate, or excessive task lists;
- meetings that are not supported by the user's objective/context.

Two guarded endpoints are added:

- `POST /api/ai/schedule/plan` generates a draft and never writes data;
- `POST /api/ai/schedule/plan/apply` validates selected draft tasks, atomically inserts non-duplicates, persists the suggested weekly focus while preserving current goals/summary, and returns the refreshed schedule.

The apply endpoint does not trust generated output merely because it came from the model. It validates every task again.

## Data contracts

Generation request:

```json
{
  "week_start": "2026-08-03",
  "objective": "Закончить лендинг и связаться с пятью клиентами",
  "intensity": "balanced",
  "include_weekend": false
}
```

Generation response:

```json
{
  "week_start": "2026-08-03",
  "week_end": "2026-08-09",
  "focus": "Завершить лендинг и запустить продажи",
  "summary": "Сначала закрываем продуктовую часть, затем выделяем блоки на поиск клиентов.",
  "tasks": [
    {
      "id": "ai-1",
      "date": "2026-08-03",
      "title": "Собрать список оставшихся блоков лендинга",
      "time": "10:00",
      "kind": "task",
      "reason": "Фиксирует объём до начала разработки"
    }
  ]
}
```

Apply request repeats `week_start`, `focus`, and selected task fields. Apply response contains `created_count`, `skipped_count`, and the refreshed `schedule` payload.

## Error handling

- Missing OpenCode Go key: HTTP 503 with a direct instruction to add it in Settings.
- Invalid week or brief: HTTP 422 with a field-level explanation.
- Provider/model failure: HTTP 502 with the existing friendly OpenCode error.
- Invalid model JSON: the existing `complete_json` retry runs once with a stricter instruction.
- Apply failure: no partial task insert; the modal remains open and announces the error with `role="alert"`.

## Testing

- Unit tests cover prompt context, normalization, date/weekend/past-day validation, duplicate removal, and invalid model payloads.
- API tests cover generation, disabled AI, guarded requests, atomic apply, duplicate skipping, and focus persistence.
- Frontend tests cover opening the planner, generating a preview, excluding a task, applying the remainder, reloading the week, and displaying provider errors.
- Full backend/frontend suites, production build, and browser QA cover light/dark modes, keyboard labels, loading states, and console errors.

## Scope exclusions

- No recurring tasks, calendar integrations, notifications, streaming response, or automatic daily replanning.
- No automatic deletion or replacement of existing tasks.
- No mobile-specific redesign; existing responsive behavior remains functional.
