# Client Retention Filters Design

## Goal

Add a non-destructive “Кто остаётся” filter to the “Волк с Уолл-стрит” client list so the user can keep only leads that satisfy explicit sales criteria.

## User experience

- A “Кто остаётся” button sits in the existing client toolbar and shows the number of active criteria.
- The button expands an inline panel above the client list; the user stays in context and sees results update immediately.
- Available criteria are minimum lead score (0–23), minimum business rating (0–5), minimum review count, required Telegram/WhatsApp/phone/e-mail, website state, and AI-message state.
- Selected criteria are combined with logical AND. If Telegram and WhatsApp are selected, a client must have both.
- Quick lead-score presets include 0, 10, 15, and 18 points so “15+” is one click.
- An active summary shows “Осталось X из Y”, human-readable filter chips, and a reset action.
- Filtering only changes the visible list. It never archives or deletes clients.

## Architecture

- Keep all filtering on the frontend because the page already loads the complete active client list and the feature changes only local visibility.
- Put pure matching and summary logic in `src/pages/clientFilters.ts` so data rules are independently testable.
- Put the disclosure panel in `src/pages/ClientRetentionFilters.tsx` so `ClientsPage.tsx` remains focused on page data and actions.
- Compose the new criteria with existing search, status, source, niche, and sort logic in the current `useMemo`.
- Store filter state only for the current page session; persistence is outside this feature.

## Matching rules

- Lead score, business rating, and review count are inclusive minimums.
- An absent rating is treated as not meeting a positive minimum rating.
- Required channels match normalized contact types. Phone also falls back to the client `phone` field.
- Website state has three values: any, missing, and present. Messaging/social links are not treated as a business website.
- AI-message state has three values: any, not generated, and generated. `ready` and `stale` both count as generated.

## Accessibility and visual behavior

- Every input has a visible label, and the disclosure button exposes `aria-expanded` and `aria-controls`.
- The result count uses `aria-live="polite"`.
- Active controls use icon and text in addition to color.
- Buttons keep visible focus states, at least 42 px height, and 150–200 ms feedback.
- Light, regular dark, and premium dark themes use existing semantic colors and Lucide icons.
- Desktop layout is primary; narrow layouts wrap controls without horizontal scrolling.

## Testing

- Unit tests cover inclusive score matching, required-channel AND semantics, website detection, rating/review thresholds, AI status, and active summaries.
- Page tests cover opening the panel, applying the 15+ and Telegram criteria, live result counts, combined filtering, and reset.
- Run the complete frontend test suite and production build. Backend behavior is unchanged, but the backend suite remains a final regression check.
