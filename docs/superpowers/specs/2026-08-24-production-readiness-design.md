# Semix CRM Production Readiness Design

**Date:** 2026-08-24  
**Status:** Approved for implementation by the user's request to bring the audited system to a polished, usable state.

## Goal

Turn Semix CRM from a capable data collector into a dependable daily work system. The release must fix confirmed broken actions, keep large datasets responsive, show the user what needs attention today, expose the existing AI profile settings, and make local data recoverable.

## Scope

This release covers five connected areas:

1. A single frontend API boundary for safe mutations and consistent errors.
2. A desktop action center on the home page using existing CRM data.
3. Progressive rendering and pagination controls for long client, job, and freelance lists.
4. Editable AI/business profile and local SQLite backup controls in Settings.
5. Accessibility, navigation, source-health, and UI feedback fixes needed for dependable daily use.

New lead sources, multi-user authentication, cloud deployment, automatic message sending, and a full backend rewrite are intentionally outside this release. The backend remains local-only on `127.0.0.1`.

## Product Model

The home page becomes **Сегодня**, the operational entry point. It answers four questions without forcing the user to inspect every module:

- Which high-value clients still need a first contact?
- Which current tasks are unfinished?
- Which fresh vacancies or freelance orders need review?
- Which parser or source requires attention?

Every item has a direct action that opens the relevant section. The existing feature cards remain below the action center as secondary navigation.

## Architecture

### Unified API client

`src/api.ts` is the only transport layer used by page components. It always sends `X-Requested-With: SemixCRM`, parses JSON and non-JSON errors, supports cancellation, and exposes typed query helpers. This removes the source of the confirmed `403` failures in Freelance.

### Action center API

A read-only endpoint, `GET /api/dashboard`, aggregates existing repositories instead of duplicating business data. Its response contains summary counters, bounded action lists, and source-health records. Each list is capped so the dashboard remains fast even when the database grows.

The endpoint does not mutate data and does not call external services. Source health comes from the latest persisted source checks.

### Progressive lists

Each large page keeps its current filters but only mounts a bounded slice of the filtered result. A reusable `ProgressiveListFooter` reports the visible count and provides “Показать ещё” and “Показать все” actions. Changing a filter resets the visible limit. This immediately fixes DOM overload without breaking the existing API contract; server pagination can be introduced later without redesigning the UI.

### Profile and backups

Settings gains two focused panels:

- **Рабочий профиль** edits the existing `/api/ai/profile` resource used by AI prompts.
- **Данные и резервные копии** creates a timestamped, consistent SQLite backup through the SQLite backup API and lists/downloads existing backups.

Backups are written only to `backend/data/backups`, use generated filenames, and cannot accept user-provided filesystem paths. Restore is deliberately excluded because it is destructive and requires a separate safeguarded workflow.

### Navigation

The active section is mirrored in the URL hash. Initial load reads a valid hash, navigation updates it, and browser Back/Forward changes the visible page. The profile button opens Settings and focuses the profile panel. The top search is visible only on the home page, where it has real meaning.

## User Experience

The established premium black desktop style remains the source of truth:

- Inter typography and the existing semantic dark tokens.
- Dense but readable dashboard spacing.
- Blue for primary navigation, green for positive progress, amber for attention, red only for failure/destructive states.
- Lucide icons only; no emoji icons.
- Visible keyboard focus, explicit loading/success/error feedback, and 150–300 ms transitions.
- No new mobile-specific feature work, but content must not become unusable at common desktop widths.

The action center prioritizes information rather than decoration: one primary headline, compact metrics, four bounded work queues, and clear empty states.

## Data Contracts

`GET /api/dashboard` returns:

```json
{
  "generated_at": "2026-08-24T10:00:00+00:00",
  "stats": {
    "clients_total": 1216,
    "clients_to_contact": 1211,
    "tasks_open": 0,
    "jobs_new": 594,
    "freelance_active": 0
  },
  "clients": [],
  "tasks": [],
  "jobs": [],
  "freelance": [],
  "source_health": []
}
```

`POST /api/backups` returns the backup metadata. `GET /api/backups` returns metadata only. `GET /api/backups/{filename}` downloads a file after strict filename validation.

## Error Handling

- Dashboard failure shows a local retry action while normal navigation remains available.
- One failed dashboard source does not crash the full page; the backend returns empty bounded lists and valid counters where possible.
- Backup failures never remove or overwrite the live database.
- Profile and backup forms keep their current values when a request fails and show the backend error near the action.
- Progressive-list actions are purely local and cannot lose data.

## Testing

- Backend tests cover dashboard aggregation, list bounds, backup creation, filename traversal rejection, and profile persistence.
- Frontend tests reproduce the Freelance `403` contract by asserting the safety header.
- Component tests cover dashboard loading/error/success, hash navigation, profile button navigation, profile save, backup creation, and progressive list behavior.
- The full backend suite, frontend suite, TypeScript build, dependency checks, database integrity check, and live browser smoke test are required before release.

## Success Criteria

- Freelance “Проверить сейчас” and source “Войти” no longer return `403`.
- The home page immediately exposes actionable work and stale/broken sources.
- Client, jobs, and freelance pages no longer mount every database row at once.
- The user can edit the identity and portfolio information used by AI.
- The user can create and download a consistent SQLite backup from Settings.
- Section URLs survive refresh and work with browser Back/Forward.
- All automated tests and the production build pass.
