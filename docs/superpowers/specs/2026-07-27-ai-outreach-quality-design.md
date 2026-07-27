# AI outreach quality and desktop dialog design

## Context

Semix CRM generates a first cold message for a client from the data stored in
the 2GIS card. The current flow asks an OpenCode Go model for JSON containing an
analysis, three message variants and a follow-up.

The failure was reproduced with the saved `mimo-v2.5-pro` configuration and the
real client `ЕвроДент`:

- OpenCode Go returned HTTP 200;
- `finish_reason` was `length`;
- `message.content` was `null`;
- the model spent the entire 1,800-token completion budget in
  `message.reasoning_content`;
- the backend converted the missing content to the string `None`, retried with
  another text-only instruction, and finally reported
  `Модель вернула ответ без JSON`.

The current dialog also gives most of its height to a long internal analysis.
The editable message and primary send actions are pushed below the fold, while
the dialog and the page create an uncomfortable nested scrolling experience.

## Goals

1. Generate three useful messages in one request:
   - a confident seller;
   - a hard-sell “Wolf of Wall Street” version;
   - a calm expert.
2. Make structured output reliable for OpenCode Go models, especially MiMo.
3. Keep every claim grounded in the client card and explicitly mark estimates
   as hypotheses.
4. Present the result as a desktop sales workspace where the chosen message and
   send actions are always easy to reach.
5. Verify the full flow with automated tests and live generations for
   `ЕвроДент` and `7R`.

## Non-goals

- Automatic message sending.
- Scraping additional facts from the client website or social networks.
- A dedicated mobile redesign.
- Generating each tone with a separate paid model request.
- Promising conversion, revenue or search-ranking results.

## Considered approaches

### One structured request for all three tones — selected

One request receives the company facts and returns all three variants in a
strict schema. This keeps facts and positioning consistent, has the lowest
latency and consumes one request from the OpenCode Go allowance.

### Three independent model requests

This could produce more creative variety, but triples latency and cost and can
produce mutually contradictory claims about the same company.

### One base message plus local rewrites

This is cheap, but rule-based rewrites tend to change vocabulary rather than
sales strategy. The three variants would feel artificial and repetitive.

## Backend design

### Model request policy

`AiClient` will build model-compatible request payloads:

- use OpenAI-compatible `response_format: {"type": "json_object"}` for
  structured completions;
- for `mimo-*`, add `chat_template_kwargs.enable_thinking: false` so the answer
  is written to `message.content` instead of exhausting the budget in
  `reasoning_content`;
- retain one repair attempt when the first response is not valid JSON;
- make the repair attempt describe the exact structural problem;
- treat `content=null`, `finish_reason=length` and an exhausted reasoning-only
  response as distinct, actionable errors in logs without exposing the API key
  or full private response.

The implementation must not parse `reasoning_content` as the final answer. It
can contain drafts and analysis that were never meant to be shown or sent.

### Response contract

The model returns one JSON object:

```json
{
  "analysis": {
    "signal": "fact from the card",
    "problem": "grounded sales hypothesis",
    "opportunity": "honest business outcome"
  },
  "variants": [
    {
      "tone": "confident",
      "title": "Уверенный продавец",
      "text": "180–320 character message"
    },
    {
      "tone": "hard_sell",
      "title": "Жёсткая продажа",
      "text": "180–320 character message"
    },
    {
      "tone": "expert",
      "title": "Эксперт",
      "text": "180–320 character message"
    }
  ],
  "follow_up": "short follow-up for day three"
}
```

The API will continue returning the existing `analysis`, `pain` and
`money_argument` fields during the transition so cached records and existing
frontend callers remain compatible. The frontend can derive its three compact
insight cards from either the new structured analysis or the legacy fields.

### Prompt strategy

The system prompt will describe one shared sales framework:

1. Start with one verifiable fact from the card.
2. Translate the missing or weak customer journey into a cautious business
   hypothesis.
3. Offer a concrete, low-friction next step.
4. End with a question that invites a useful reply.

The three tones must change the strategy, not merely swap adjectives:

- **Confident:** direct, concise and commercially focused.
- **Hard sell:** sharper contrast, urgency and money framing, but no insults,
  intimidation, false scarcity or invented losses.
- **Expert:** diagnostic, calm and helpful, with evidence before the offer.

Messages must:

- be 180–320 characters including the signature;
- use the executor profile for the offer and signature;
- avoid links, markdown, lists, clichés and unsupported guarantees;
- say “не вижу сайта в карточке” instead of claiming that a business definitely
  has no website;
- use conditional language for financial estimates;
- avoid claiming that online booking, prices or a particular competitor exists
  unless the card proves it.

### Validation and repair

The validator requires exactly one non-empty variant for each of
`confident`, `hard_sell` and `expert`. It normalizes whitespace, removes links
and markdown, rejects banned phrases, verifies the length range and checks for
an open question.

If the first payload is invalid, the backend sends one repair request containing
only the validation errors and the required schema. If the repaired payload is
still invalid, the API returns a readable error with a suggestion to regenerate
or choose another model. Invalid results are never cached.

## Desktop interface design

The client-message dialog becomes a wide desktop workspace with a maximum
height that fits inside the viewport.

### Header

- Sparkles icon, “Первое сообщение” and the company name.
- Small model/status metadata.
- Close button with a visible hover and keyboard focus state.

### Main content

The dialog uses two columns:

- **Left column:** three compact cards — signal, sales hypothesis and possible
  business outcome. This column summarizes the reasoning and does not scroll
  independently.
- **Right column:** three clearly named tabs for the tones, a prominent editable
  message field, character counter and small tone description.

The first selected tone is `confident`. Switching tabs keeps edits made to each
variant during the current dialog session.

### Actions

A sticky footer keeps these actions visible:

- copy;
- open WhatsApp;
- open Telegram;
- regenerate all three variants.

The follow-up is a compact secondary panel below the editor instead of a large
always-expanded block. Model warnings appear next to the relevant message, not
as a generic wall of text.

### States and accessibility

- Loading uses a clear progress state and disables duplicate generation.
- AI errors stay inside the dialog and offer “Повторить”.
- Tabs expose correct tab roles and keyboard selection.
- Every icon-only control has an accessible name.
- Light and dark themes retain readable contrast and visible focus rings.
- The desktop layout must not create nested scrollbars at the target viewport
  used by the current CRM.

## Data flow

1. The dialog requests a cached result.
2. If none exists, it requests one structured generation.
3. `AiClient` applies the model compatibility policy.
4. The outreach service validates or repairs the response.
5. Only a valid normalized result is cached.
6. The frontend renders compact insights and the three editable tone variants.
7. Copying or opening a messenger always uses the currently selected, possibly
   edited text.

## Testing

### Backend

- MiMo requests disable thinking and request JSON output.
- `content=null` is not converted to the literal string `None`.
- reasoning-only and length-exhausted responses produce useful diagnostics.
- malformed JSON triggers one repair request.
- the validator requires exactly the three tone identifiers.
- unsupported facts, links, banned phrases and invalid lengths are rejected or
  normalized as designed.
- legacy cached payloads remain readable.

### Frontend

- the three tone tabs render with the expected names;
- the confident variant is selected first;
- edits remain isolated per variant;
- copy and messenger links use the selected edited text;
- errors expose a retry action;
- compact insight cards replace the long analysis block;
- the footer actions remain available without scrolling the whole dialog.

### Live verification

- Generate with the saved OpenCode Go key for `ЕвроДент` and `7R`.
- Confirm valid JSON, exactly three tones and grounded facts.
- Review every generated message for length, specificity, honesty and a useful
  next step.
- Inspect the dialog in the running desktop browser in light and dark themes.
- Run the complete backend and frontend suites and the production build before
  committing the implementation.

## Acceptance criteria

- The reproduced `Модель вернула ответ без JSON` failure no longer occurs with
  the saved `mimo-v2.5-pro` configuration.
- A single generation returns all three approved sales styles.
- No generated message contains invented company facts or unqualified revenue
  promises.
- The selected message and send actions are visible and usable in the desktop
  dialog without the current double-scroll layout.
- Real generations for `ЕвроДент` and `7R`, automated tests and the production
  build all complete successfully.
