# Unlimited 2GIS Parsing Design

## Goal

Let the “Волк с Уолл-стрит” parser collect every company in a 2GIS search, for example every dentistry in Novosibirsk, instead of stopping at 50 records.

## Upstream behavior

- SemixCRM uses `interlark/parser-2gis` version 1.2.1.
- The upstream parser already walks forward through the available 2GIS result pages and stops when no next page exists.
- Upstream requires `parser.max_records` to be a positive integer and uses it only as an early-stop counter; it has no native unlimited sentinel.
- SemixCRM will therefore represent unlimited mode as `limit = 0` in its own API and persistence layer, then pass `2_147_483_647` to upstream. A normal 2GIS result set reaches its final page long before that technical ceiling.

## User experience

- Replace the 1–50 range slider with a two-option scope control: “Все компании” and “Указать лимит”.
- “Все компании” is available whenever 2GIS is selected and explains that the parser will continue to the end of the 2GIS result set.
- “Указать лимит” exposes a numeric input without the old 50-company ceiling.
- The selected start page remains independent: unlimited mode starts at that page and continues through the last available page.
- If both 2GIS and Yandex Maps are selected, unlimited mode applies to 2GIS while Yandex Maps keeps its existing safe maximum of 50 records per niche. The helper text states this explicitly.
- If 2GIS is removed while unlimited mode is active, the panel switches to the finite 50-record mode so the UI never promises unlimited Yandex parsing.
- Running state and saved settings remain visible through the existing parser status and feedback controls.

## Data contract

- `limit = 0` means “all available 2GIS companies”.
- `limit >= 1` means an explicit per-niche, per-source record limit.
- The settings and parse request APIs accept every non-negative integer and persist it without clamping to 50.
- Existing saved positive limits remain unchanged; the change does not silently turn an old limited run into a potentially long unlimited run.
- Parser run history stores `0` for unlimited launches, preserving exactly which mode was used.

## Runtime behavior

- Limited 2GIS runs pass their requested value to `--parser.max-records` without the existing 200-record clamp.
- Unlimited 2GIS runs pass the upstream-compatible technical ceiling and do not use SemixCRM’s old ten-minute whole-process timeout.
- Limited runs receive a duration proportional to the requested record count rather than the previous 600-second ceiling.
- JSON loading and cross-source deduplication do not slice an unlimited result set.
- Temporary parser output is still deleted after import unless the existing debug environment flag asks to keep it.
- Partial-source error behavior remains unchanged.

## Accessibility and visual behavior

- Scope options are native buttons in a labelled group and expose their selected state with `aria-pressed`.
- The finite numeric input has a visible label, integer minimum, clear focus state, and no artificial maximum.
- Selected state uses text, icon, border, and color rather than color alone.
- Styling follows the existing dense SemixCRM design system and supports light, dark, and premium-dark themes.
- Desktop is primary; the control may wrap on narrow screens without horizontal overflow.

## Testing

- Backend tests prove that `limit = 0` is accepted and persisted, unlimited 2GIS receives the technical ceiling and no global timeout, positive values above 50 are preserved, JSON results are not truncated, and aggregate deduplication retains all records.
- Frontend tests prove that “Все компании” saves and starts with `limit = 0`, and that a custom value above 50 is sent unchanged.
- Existing backend and frontend suites plus the production build provide regression coverage.
- A live parser smoke test uses the real 2GIS runtime with “стоматологии” in Novosibirsk and confirms that collection progresses beyond the former 50-company boundary. The smoke test writes to a disposable parser output and does not add test records to the CRM database.
