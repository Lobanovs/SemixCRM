# Manual AI outreach and 2GIS review evidence design

## Context

The client list currently exposes a `Написать` action. Opening the dialog checks
for a cached result and, when none exists, immediately starts a paid OpenCode Go
generation. This hides the distinction between viewing a saved draft and asking
the model to create a new one.

The client rows also do not show whether a message has already been generated.
As a result, the user cannot scan the list and see which leads are ready for
outreach.

The current prompt overuses rating and review counts. A message such as
`У вас 229 отзывов и рейтинг 4.8` is factually correct but still feels like a
mass mailing because it does not demonstrate that the sender looked at the
business. The 2GIS public review page contains real review texts, so the system
can use a supported detail such as a frequently praised specialist, atmosphere
or service quality instead of inventing personalization.

## Goals

1. Opening a client message must never start generation automatically.
2. Every client row must show whether its AI text is missing, ready or stale.
3. The dialog must provide one explicit `Сгенерировать 3 текста` action.
4. The recommended variant must follow the approved long-form sales structure:
   real review evidence, an observable conversion gap, a concrete site offer,
   optional portfolio proof and a low-pressure next step.
5. The system must read a small set of real public 2GIS reviews and never invent
   their contents.
6. The portfolio link
   `https://semyon-lobanov-portfolio.vercel.app/` must be available by default
   and removable without another model request.
7. Personal demo sites are out of scope.

## Non-goals

- Generating a unique demo site for every lead.
- Automatically sending a message.
- Claiming that a company has no website outside the observed 2GIS card.
- Quoting reviewer names or long verbatim review passages in outreach.
- Blocking generation when 2GIS reviews are temporarily unavailable.
- A dedicated mobile redesign.

## Considered approaches

### Rating and review count only

This is fast and reliable because the data is already stored, but it produces
generic copy and does not prove that the sender studied the business.

### Let the model infer likely review themes

This is rejected. It would produce fluent but unsupported claims about staff,
cleanliness, service or atmosphere.

### Fetch real reviews and preserve evidence — selected

At generation time the backend reads up to seven useful public reviews from the
client's 2GIS review page. The model receives numbered excerpts and must return
the identifiers that support its summary. The backend validates those
identifiers before accepting the message. If fetching fails, generation
continues without a review-specific claim and reports a small warning.

This gives the strongest personalization without requiring a demo site or
manual research for every lead.

## Approved sales strategy

The primary variant is `По отзывам и точке роста`. It uses five short blocks:

1. Greeting and proof of research.
2. A concrete detail supported by real 2GIS reviews.
3. A cautious description of the missing customer path visible in the card.
4. A clear site outcome: services, prices, online request and administrator
   notification.
5. Optional portfolio proof and a low-friction reply CTA.

The approved reference copy is:

> Здравствуйте!
>
> Посмотрел карточку Cosmo в 2GIS и почитал отзывы. Обратил внимание, что
> клиенты особенно часто отмечают [конкретная подтверждённая деталь]. Видно,
> что у вас уже сложилась хорошая репутация и люди вам доверяют.
>
> При этом я не увидел отдельного сайта, где можно спокойно посмотреть все
> услуги, цены и оставить заявку. Если человек выбирает вечером или пока не
> готов звонить, он может просто закрыть карточку и продолжить поиск.
>
> Я разрабатываю сайты для бизнеса и могу сделать для Cosmo понятный сайт с
> услугами, ценами и онлайн-записью. Новые заявки будут сразу приходить
> администратору в мессенджер или на почту.
>
> Примеры моих работ:
> https://semyon-lobanov-portfolio.vercel.app/
>
> Если сайт для вас сейчас актуален, просто ответьте «да» — пришлю варианты по
> стоимости и срокам без созвона и длинной презентации.

The generated message uses the real company name, niche and verified evidence.
It must say `в карточке 2GIS не увидел отдельного сайта` rather than claiming
that the business definitely has no site.

The other two variants are:

- `Решение и портфолио`: a more direct commercial offer with the proof link
  closer to the solution.
- `Короткий контакт`: a compact first touch with one supported observation and
  one simple question.

The old `Жёсткая продажа` framing is removed because it makes an unsolicited
first contact feel adversarial and lowers trust.

Target lengths exclude the optional standard portfolio block:

- `По отзывам и точке роста`: 650–1,100 characters;
- `Решение и портфолио`: 450–800 characters;
- `Короткий контакт`: 220–380 characters.

The long variants use short paragraphs instead of compressing the entire
message into one wall of text.

## Review evidence design

### Retrieval

The backend derives a 2GIS review URL only from a trusted `2gis.ru/firm/<id>`
client card URL. It downloads the public review page with a strict timeout,
bounded response size and a normal browser user agent.

The page contains structured review data. The extractor keeps at most seven
non-empty customer review texts and excludes obvious business-owner replies,
advertising blocks and duplicate content. Stored excerpts are bounded in
length.

### Model contract

Reviews are sent as numbered evidence, for example:

```text
[R1] Хорошее место... качество отличное...
[R2] ...приятная атмосфера... с любовью к своему делу...
[R3] ...умеют найти к клиенту подход...
```

The structured model response includes:

```json
{
  "review_insight": {
    "summary": "Клиенты отмечают качество процедур и внимательное отношение",
    "evidence_ids": ["R1", "R3"]
  }
}
```

Every evidence identifier must exist in the supplied review set. When no
reviews are available, `summary` and `evidence_ids` are empty and the message
must not claim that reviews were read.

The review excerpts become part of the AI input fingerprint so a materially
changed evidence set invalidates the cached result.

### Failure behaviour

- A network, parsing or 2GIS layout failure does not fail the entire generation.
- The prompt falls back to stored rating, count and other card facts.
- The result contains a warning that review-specific personalization was not
  available.
- Unsupported review claims make the model response invalid and trigger the
  existing single repair attempt.

## Portfolio behaviour

The model never writes URLs. The backend returns the configured
`portfolio_url` separately and the frontend owns a standard portfolio block:

```text
Примеры моих работ:
https://semyon-lobanov-portfolio.vercel.app/
```

The dialog switch `Добавить портфолио` is on by default. Switching it off
removes only this standard block from all three editable drafts. Switching it
back on inserts the block immediately before the final CTA. This operation is
local and does not call OpenCode Go or overwrite other user edits.

The existing AI profile remains the source of truth. Its default portfolio URL
is updated to the approved URL, and the user can still change it in settings.

## Client-list status

`GET /api/clients` returns these additional fields:

- `ai_message_status`: `missing`, `ready` or `stale`;
- `ai_message_created_at`: ISO timestamp or an empty string.

The status is calculated in one batched AI-result lookup, not with one database
query per client:

- `missing`: no saved client-message result exists;
- `ready`: the saved input fingerprint matches the current client data,
  executor profile, prompt version and review evidence fingerprint stored with
  the result;
- `stale`: a result exists but its input no longer matches.

Review retrieval is not performed while listing clients. The last evidence
fingerprint stored with the result is reused for the status check; a new review
fetch happens only when the user explicitly generates again.

The row renders:

- grey `Текст не готов`;
- green `Текст готов` plus the generation date;
- amber `Нужно обновить`.

The action is always named `Посмотреть текст`. When a message is generated or
regenerated, the modal reports the new status to the list so the badge updates
without a full page reload.

## Dialog states and flow

### Empty state

Opening `Посмотреть текст` performs only a cached-result GET. If no current
result exists, the dialog shows:

- company name and the grounded facts already available;
- optional input `Что вы заметили` for a manually verified observation;
- enabled `Добавить портфолио` switch;
- explanation that up to seven public 2GIS reviews will be checked;
- primary button `Сгенерировать 3 текста`.

No POST request is issued until that button is pressed.

### Loading

The primary action becomes `Читаю отзывы и готовлю тексты…`, duplicate clicks
are disabled and the dialog remains open.

### Ready state

The existing desktop workspace remains, with renamed strategies and a review
evidence card in the left column. The selected draft is editable. Copy,
WhatsApp and Telegram always use the visible edited text including or excluding
the standard portfolio block.

### Error and stale states

Generation errors stay in the dialog and keep the user's manual observation.
A stale saved result is not presented as current; the empty-state action reads
`Обновить 3 текста`.

## API changes

The generation request uses JSON:

```json
{
  "manual_observation": ""
}
```

`manual_observation` is optional, trimmed and length-limited. The portfolio
switch does not belong in the generation request because portfolio insertion is
deterministic and local.

The cached-result GET remains read-only and never invokes the model.

The generation response keeps the current compatibility fields and adds:

- `review_insight`;
- `review_evidence`;
- `portfolio_url`;
- the new strategy identifiers and titles.

## Testing

### Backend

- Extract useful customer review texts from a saved 2GIS page fixture.
- Reject unsupported card URLs and owner replies.
- Continue generation when review retrieval fails.
- Put numbered review evidence and a manual observation into the prompt.
- Require valid evidence identifiers in the response.
- Reject review claims when no evidence was supplied.
- Generate the approved long-form primary structure.
- Keep the missing-site wording scoped to the 2GIS card.
- Batch client AI statuses without per-client database connections.
- Invalidate the cache when client data, profile, prompt version or manual
  observation changes.

### Frontend

- Opening the dialog with no cache performs GET but no POST.
- The empty state exposes `Сгенерировать 3 текста`.
- Clicking generation sends one POST and renders all three strategies.
- Client rows show missing, ready and stale badges.
- The row status updates after successful generation.
- The portfolio switch adds and removes the standard block without another
  model request.
- Manual edits survive portfolio toggling.
- Copy and WhatsApp use the currently visible edited text.
- Loading, disabled-AI and error states remain accessible.

### Live verification

- Generate for `Cosmo` and confirm the review detail is supported by the
  displayed evidence.
- Generate for one client whose review page is unavailable and confirm the
  fallback contains no invented review detail.
- Verify that opening a never-generated client creates no OpenCode Go request.
- Inspect missing, ready and stale badges and the dialog in the running desktop
  browser.
- Run the complete backend suite, frontend suite and production build.

## Acceptance criteria

- `Посмотреть текст` never triggers generation.
- A user can see message readiness directly on every active client row.
- The primary generated message follows the approved Cosmo structure and cites
  a real review theme.
- Every review-specific statement has valid evidence from the same 2GIS card.
- Portfolio inclusion is enabled by default and can be toggled locally.
- Failure to retrieve reviews degrades safely instead of blocking outreach.
- No personal demo site is required or promised.
- All automated tests, the production build and live desktop verification pass
  before the implementation is pushed to `main`.
