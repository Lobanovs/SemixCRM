# Schedule Task CRUD Design

## Goal

Make the weekly schedule support complete, obvious task CRUD from the desktop UI without crowding the seven narrow day columns.

## Confirmed interaction model

- Clicking a day header or its empty task area opens task creation with that date preselected.
- Clicking a task title/card opens the same modal in edit mode.
- Clicking the task checkbox only toggles completion and never opens the editor.
- Edit mode can update title, date, time, and kind.
- Edit mode includes a destructive delete action with an explicit confirmation step.
- The global “Добавить задачу” actions continue to open creation for the currently selected date.

## Approaches considered

1. **Shared create/edit modal — selected.** Fits the existing UI, keeps all fields visible, preserves the dense week board, and provides room for a safe delete confirmation.
2. **Inline editing inside each day column.** Saves one click, but makes seven narrow columns jump in height and creates accidental edits near completion controls.
3. **Right-side task drawer.** Scales to richer task details, but adds unnecessary navigation and layout complexity for the current four task fields.

## Frontend structure

`SchedulePage` owns the selected day and the task being edited. One `TaskModal` accepts either an existing task or a default date:

- no task: creation mode, `POST /api/schedule/tasks`;
- existing task: edit mode, `PUT /api/schedule/tasks/{id}`;
- confirmed delete: `DELETE /api/schedule/tasks/{id}`.

`WeekColumn` exposes separate callbacks for day creation, completion toggle, and task editing. A day-level add affordance is always visible in the header; the empty task area is also clickable. Task cards use a real checkbox-style button with an accessible label, while the remaining card surface is a separate edit button.

After every successful mutation, the week is reloaded from the API so counters, upcoming events, ordering, and statistics remain authoritative. If an edited task moves to another week, the UI follows its new date.

## Visual and accessibility behavior

- Day columns show a subtle hover/focus state and a compact plus button with a minimum 40–44 px target where space permits.
- Task edit and completion controls have independent accessible names.
- The delete action uses the existing red semantic styling and requires a second confirmation click inside the modal.
- Errors stay inside the modal for create/edit/delete failures; the modal remains open so entered values are not lost.
- Successful create, edit, delete, and completion operations announce status through the existing schedule toast.
- Light and dark themes reuse existing Semix CRM tokens and styles; desktop remains the primary layout.

## Backend scope

The required routes and database operations already exist:

- `POST /api/schedule/tasks`;
- `PUT /api/schedule/tasks/{task_id}`;
- `DELETE /api/schedule/tasks/{task_id}`.

No schema migration is required. Backend regression tests will explicitly cover editing all task fields, deletion, and a missing-task `404` response.

## Test plan

Frontend tests will prove that:

1. clicking a chosen weekday opens creation with the correct date;
2. submitting creation sends the expected POST body;
3. clicking a task opens populated edit mode and PUT persists changed fields;
4. completion uses a separate PUT containing only `done`;
5. deletion requires confirmation and sends DELETE;
6. API failures are shown without closing the editor.

Backend tests will cover create/read/update/delete persistence and API `404` behavior. Final verification includes the full Python suite, full Vitest suite, production build, and manual browser interaction against the running local API.
