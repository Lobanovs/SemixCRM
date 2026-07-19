# Semix CRM: parser history and archived clients

## Goal

Make every parser launch auditable and make the client's "clear" action reversible. The product must show the exact records returned by each launch, preserve duplicate outcomes, and give the user a compact, readable parser settings dialog.

## User experience

### Parser settings

- A modal is constrained to the viewport and uses an internal scroll region.
- City is selected from the existing major-city list.
- Niches are selected from the existing curated list. A small search field filters the list; there is no free-form niche input.
- Sources are presented as compact toggle cards for 2GIS and Yandex Maps.
- The footer stays visible with the selected niche count, limit, error text, and save action.

### Run history

- The parser panel has a clear “Открыть всю историю” action.
- The history view lists launches newest first and supports search plus source/status filters.
- Each launch displays time, city, niches, sources, parsed count, newly added count, duplicate count, and status.
- Selecting a launch opens a detail view containing the immutable result snapshot. Every result shows name, niche, city, source link, rating, review count, score, contacts, and whether it was inserted or already existed.
- If a run predates snapshot storage, the detail view explicitly says that exact per-result data was not captured for that legacy run; it must not invent a list.

### Archived clients

- “Скрытые клиенты” is a separate view reachable from the client toolbar and from the clear confirmation message.
- It lists archived records with the same lead evidence as the active list and shows the archived date.
- Each record can be restored. A single “Восстановить всех” action restores all archived records after confirmation.
- Restoring never creates a duplicate and does not alter parser history snapshots.

## Backend contract

The existing `clients` and `parser_runs` tables remain backward compatible. A new `parser_run_results` table stores one row per parser input with:

- `run_id`, `client_id`, `outcome` (`inserted` or `duplicate`), stable `position`, UTC timestamp;
- `snapshot_json`, the fully enriched lead at parse time (including rating, reviews, contacts, card URL, source, score, and score reasons).

The parser run API includes `parsed_count`, `result_count`, and `snapshot_available`. `GET /api/parser/runs/{run_id}` returns metadata plus ordered result snapshots. Archive endpoints expose list, single restore, and restore-all operations.

The insertion path calculates dedupe once per input, updates an existing record when appropriate, and returns an ordered per-input result. An archived duplicate remains archived. The background job saves that result before marking the run complete and returns only that run's result clients to the polling endpoint.

## Data and compatibility

- Existing runs remain readable. Runs without rows in `parser_run_results` are marked as legacy and show the explanatory empty state.
- Existing active/archived client rows and their scores/contacts are preserved.
- All timestamps are stored as UTC ISO-8601 strings.
- Snapshot JSON is treated as untrusted display data; URLs are validated by the existing frontend safe-link helper.

## Visual and accessibility rules

- The UI keeps the established Semix CRM visual language: white/indigo cards, 8px radius, blue primary action, green success state.
- Body text is at least 14px in detail views; cards use predictable grid columns and `minmax(0, 1fr)` to prevent overlap.
- Modal controls have at least 40px hit targets, visible focus states, labels, and keyboard-operable custom checkboxes.
- Dark theme styles cover new views, modal controls, result cards, badges, links, and empty states.
- The modal never exceeds `calc(100vh - 40px)` and only its body scrolls.

## Verification

- Backend unit tests cover archive/restore, inserted-vs-duplicate snapshot ordering, and legacy runs.
- TypeScript build must pass.
- The local frontend is inspected in the in-app browser at desktop size. The parser settings modal is measured for viewport containment and two-column niche layout; history and archive are opened and interacted with; browser console errors are checked.
