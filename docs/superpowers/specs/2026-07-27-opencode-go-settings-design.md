# OpenCode Go Settings Design

**Date:** 2026-07-27
**Status:** Approved for implementation

## Goal

Replace the placeholder “Настройки” section with a working OpenCode Go configuration screen. The user must be able to paste an OpenCode Go API key, choose a supported model, verify the connection, save the configuration, and use it immediately for AI-generated client messages without restarting the backend.

## Scope

The feature supports OpenCode Go only. It does not add arbitrary OpenAI-compatible providers.

The settings screen contains:

- a masked OpenCode Go API-key field with show/hide control;
- a model selector limited to models supported by the existing `chat/completions` client;
- a request-timeout field;
- a fixed, read-only OpenCode Go endpoint;
- connection state: not configured, connected, or error;
- actions to save, test, and remove the saved API key;
- clear inline validation and request feedback.

## Architecture

### Backend storage

AI settings are stored in the local SQLite database under `backend/data/`, which is excluded from Git. The API key is never returned by a read endpoint. The frontend receives only whether a key exists and a short masked hint.

Environment variables remain a compatibility fallback. Database values take precedence, so a setting saved from the UI is applied on the next AI request without a backend restart.

Stored values:

- `api_key`;
- `model`;
- `timeout`;
- `updated_at`.

The OpenCode Go base URL is a code constant and is not user-editable.

### Backend API

- `GET /api/ai/settings` returns the safe public configuration.
- `PUT /api/ai/settings` validates and stores the model, timeout, and optional replacement key.
- `DELETE /api/ai/settings/key` removes the database key.
- `POST /api/ai/settings/test` validates the effective or newly supplied key against OpenCode Go and returns a concise status.

Powerful-action protection is applied to all mutating and connection-test endpoints. Error responses distinguish a rejected key, unavailable service, rate limiting, and invalid input.

### AI client integration

`load_settings()` reads database configuration first and environment variables second. Existing outreach generation continues to use the same `AiClient`, so no client-message workflow needs a separate configuration path.

The obsolete `qwen3-coder` default is replaced with a currently available OpenCode Go `chat/completions` model. The UI offers only compatible model IDs; models that require the Anthropic-style `/messages` endpoint are excluded from this feature.

## Frontend

A new `SettingsPage` replaces the placeholder. It follows the existing Semix CRM dashboard style and supports light and dark themes.

The page is organised as:

1. Header and a short explanation of what OpenCode Go enables.
2. Connection-status card.
3. Configuration form with visible labels and helper text.
4. Save, test, and remove-key actions.
5. A compact note explaining that the secret stays on the local computer and is not committed to Git.

The key input starts empty even when a key is already configured. Leaving it empty preserves the existing key. Removing a key requires explicit confirmation.

## Data Flow

1. Opening the page loads safe settings from `GET /api/ai/settings`.
2. Saving submits model, timeout, and a key only when the user entered a new one.
3. The backend validates and persists the values, then returns the safe representation.
4. Testing uses the entered unsaved key when present; otherwise it uses the saved effective key.
5. AI client-message generation reads the latest effective settings on every request.

## Validation and Error Handling

- API key is trimmed and rejected when explicitly submitted as blank.
- Model must be one of the supported OpenCode Go `chat/completions` model IDs.
- Timeout is constrained to a practical numeric range.
- The secret is excluded from logs and API responses.
- Save/test buttons show pending state and cannot be double-submitted.
- Errors appear next to the form as an accessible alert.
- Successful save and connection checks provide explicit confirmation.

## Testing

Backend tests cover:

- safe settings retrieval without exposing the key;
- database precedence and environment fallback;
- saving a new key and preserving a stored key when the field is omitted;
- deleting the stored key;
- validation of model and timeout;
- successful and failed connection checks;
- immediate use of saved settings by `AiClient`.

Frontend tests cover:

- loading and rendering safe settings;
- saving a key and configuration;
- preserving an existing key when no replacement is entered;
- connection-check feedback;
- confirmed key removal;
- validation and backend error display.

Final verification includes the complete backend suite, complete frontend suite, production build, and a manual browser check of the settings workflow without exposing a real API key.

## Security Boundary

Semix CRM is a local single-user application. The API key is stored in the ignored local SQLite database and is not sent anywhere except OpenCode Go during a connection check or AI request. The key is not encrypted at rest; anyone with access to the local database and operating-system account can retrieve it. The UI and API prevent accidental disclosure, but they are not a substitute for operating-system disk and account protection.
