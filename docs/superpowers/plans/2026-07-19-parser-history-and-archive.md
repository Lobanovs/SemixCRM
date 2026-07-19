# Parser History and Archive Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Persist exact parser result snapshots, expose reversible client archive workflows, and align the parser settings/history UI with the Semix CRM visual system.

**Architecture:** Extend the existing SQLite repository with a `parser_run_results` append-only table. The FastAPI job writes an ordered snapshot for every parsed input (new or duplicate), while the React page consumes list/detail/archive endpoints and renders separate views without changing the existing app router.

**Tech Stack:** React + TypeScript + Vite, FastAPI + Pydantic, SQLite, Python `unittest`, in-app browser automation.

## Global constraints

- Work in the current SemixCRM workspace/main branch because the user explicitly requested direct implementation, commits, and frontend verification in this project.
- Preserve existing Russian product copy and active client data; archive is reversible and never deletes rows.
- Use `apply_patch` for edits. Keep all URLs behind the existing `safeHref` helper.
- Follow TDD: add focused failing backend tests, run them to observe failure, then implement the smallest production changes.
- Keep parser snapshots immutable; updating a client status must not rewrite historical result JSON.

## Task 1: capture the approved design

Files: `docs/superpowers/specs/2026-07-19-parser-history-and-archive-design.md`, this plan.

- Review the spec for contradictions, placeholders, or missing acceptance criteria.
- Commit the design documents with `docs: define parser history and archive`.

## Task 2: write failing backend tests first

Files: `backend/tests/__init__.py`, `backend/tests/test_parser_history.py`.

- Use a temporary SQLite path and call `init_db()` for isolation.
- Test that archiving removes a client from the active list, exposes it in the archived list, and restore returns it.
- Test that one inserted lead plus a duplicate returns two ordered results, saves both snapshots with `inserted`/`duplicate` outcomes, and returns them from a run detail query.
- Test that an old run without result rows reports `snapshot_available=False`.
- Run `backend\\.venv\\Scripts\\python.exe -m unittest backend.tests.test_parser_history -v`; record the expected import/API failures before implementation.

## Task 3: implement the persistence/API contract

Files: `backend/database.py`, `backend/main.py`.

- Add the `parser_run_results` table and a `parsed_count` migration column; enable foreign keys for run cleanup.
- Extend serialization with archive metadata and run metadata with parsed/result counts and snapshot availability.
- Add `list_archived_clients`, `restore_client`, `restore_all_clients`, `save_parser_run_results`, and `get_parser_run`.
- Make `insert_clients` return ordered per-input result records containing client id, outcome, and enriched snapshot while retaining legacy aggregate fields.
- Add archive/restore routes and `GET /api/parser/runs/{run_id}`.
- Save snapshots inside `_run_job`, set its polling response to only this run's clients, and update parsed/new/duplicate counts consistently.
- Re-run the focused unit tests, then run the complete backend test discovery.

## Task 4: implement the parser settings, history, and archive UI

Files: `src/pages/ClientsPage.tsx`, `src/styles.css`.

- Add `clients`, `history`, and `archive` view state plus typed run/detail/archive API models.
- Fetch active clients/stats, archived clients, and parser run summaries; handle loading/errors without hiding the existing parser message.
- Replace the passive history list with a navigable history view, filter controls, run selection, legacy notice, and exact result cards with contacts/ratings/reviews/source links.
- Add an archive view with restore-one and restore-all actions; make clear confirmation link to it.
- Redesign the parser settings modal with semantic header/body/footer, compact custom checkboxes, niche search, internal scroll, and stable source/limit controls.
- Add responsive/dark-theme styles for every new class and prevent grid/text overlap with `minmax(0, 1fr)`.

## Task 5: verify behavior and visual layout

- Run focused and full backend tests plus `npm run build`.
- Restart the exact stale Vite/uvicorn processes on ports 5173/8000 so the browser receives current CSS and code.
- Use the in-app browser to open Wolf page, measure modal height/grid display at 1280×720, save settings, open history, select a run, open archive, restore a client, and confirm the active list updates.
- Inspect browser console logs and take screenshots of the settings modal, history detail, and archive view.
- Fix any issue found, re-run tests/build/browser checks, and only then claim completion.

## Task 6: commit and publish

- Commit backend tests/persistence as `feat: persist parser run snapshots`.
- Commit UI as `feat: add parser history and client archive views`.
- Run `git status`, review the final diff, push `main` to the configured private GitHub remote, and report commit hashes and verification evidence.
