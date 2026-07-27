# AI Outreach Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OpenCode Go reliably generate three strong, fact-grounded sales messages and replace the cramped client-message modal with a clear desktop sales workspace.

**Architecture:** Keep one OpenAI-compatible request per generation, but make `AiClient` apply model-specific structured-output settings and preserve response metadata for useful errors. Keep sales prompting and schema validation inside the outreach module, version the prompt input to invalidate legacy cache entries, and give the React modal a dedicated stylesheet with a two-column desktop layout.

**Tech Stack:** Python 3.13, FastAPI, httpx, SQLite, unittest, React, TypeScript, Vitest, Testing Library, Vite, CSS.

## Global Constraints

- Generate `confident`, `hard_sell` and `expert` variants in one model request.
- Each final message is 180–320 characters including the signature.
- Never parse `reasoning_content` as the final answer.
- Never invent company facts, competitors, booking capabilities or guaranteed revenue.
- Use “не вижу сайта в карточке” when the card has no website.
- Keep existing cached/API fields readable while new generations use the new tone schema.
- Optimize for the desktop CRM; prevent nested modal scrollbars at the current viewport.
- Do not expose the API key or full private model response in logs or errors.

---

## File map

- `backend/ai/client.py`: OpenCode request payload policy, response extraction and one structured-output repair.
- `backend/ai/prompts.py`: sales framework, three-tone JSON contract and card-grounding rules.
- `backend/ai/outreach.py`: prompt versioning, schema normalization, length/tone validation and cache-safe result shape.
- `backend/tests/test_ai_outreach.py`: transport, prompt, validator, compatibility and regression coverage.
- `src/pages/ClientMessageModal.tsx`: desktop message workspace and interaction states.
- `src/pages/ClientMessageModal.css`: isolated light/dark desktop modal styles.
- `src/pages/ClientMessageModal.test.tsx`: tab, editing, action, error and legacy-payload behavior.
- `src/styles.css`: remove the superseded client-message modal rules.
- `README.md`: document the three-tone flow and MiMo compatibility behavior.

---

### Task 1: Reliable OpenCode structured completions

**Files:**
- Modify: `backend/ai/client.py`
- Test: `backend/tests/test_ai_outreach.py`

**Interfaces:**
- Consumes: `AiSettings.model`, `_post(payload) -> httpx.Response`.
- Produces: `AiClient.complete(..., json_mode: bool = False) -> str` and `AiClient.complete_json(..., validate: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]`.

- [ ] **Step 1: Add failing response-policy tests**

Add tests that use a transport which records the payload and can return an
exact OpenAI-compatible response:

```python
class RawResponseTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> httpx.Response:
        self.payloads.append(payload)
        body = self.responses.pop(0)
        return httpx.Response(200, json=body)


def completion(content: Any, *, finish_reason: str = "stop", reasoning: str | None = None) -> dict[str, Any]:
    return {
        "choices": [{
            "finish_reason": finish_reason,
            "message": {
                "role": "assistant",
                "content": content,
                "reasoning_content": reasoning,
            },
        }],
    }
```

Cover these assertions:

```python
self.assertEqual({"type": "json_object"}, transport.payloads[0]["response_format"])
self.assertEqual(
    {"enable_thinking": False},
    transport.payloads[0]["chat_template_kwargs"],
)
self.assertNotIn("chat_template_kwargs", non_mimo_transport.payloads[0])
```

Also assert that `content=None`, `reasoning_content` present and
`finish_reason="length"` raises an `AiError` containing
`лимит ответа ушёл на внутреннее рассуждение`, never the literal `None`.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_outreach.AiClientTests -v
```

Expected: failures because `json_mode`, `response_format`,
`chat_template_kwargs` and reasoning-only diagnostics do not exist.

- [ ] **Step 3: Implement request and response policy**

Update `complete` so its payload construction contains:

```python
def complete(
    self,
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 1600,
    *,
    json_mode: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "model": self.settings.model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if self.settings.model.casefold().startswith("mimo-"):
        payload["chat_template_kwargs"] = {"enable_thinking": False}
```

Extract the response without stringifying `None`:

```python
choice = data["choices"][0]
message = choice["message"]
content = message.get("content")
if content is None:
    reasoning = message.get("reasoning_content")
    if reasoning and choice.get("finish_reason") == "length":
        raise AiError(
            "Модель исчерпала лимит ответа на внутреннее рассуждение. "
            "Повторите запрос или выберите другую модель."
        )
    raise AiError("Модель вернула ответ без итогового текста")
if not isinstance(content, str) or not content.strip():
    raise AiError("Модель вернула пустой ответ")
return content
```

Make `complete_json` pass `json_mode=True`. Add a `validate` callback, call it
after parsing, and include the first exception text in the single repair prompt:

```python
def parse_and_validate(raw: str) -> dict[str, Any]:
    payload = extract_json(raw)
    if validate is not None:
        validate(payload)
    return payload
```

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run the same unittest command. Expected: all `AiClientTests` pass.

- [ ] **Step 5: Commit and push**

```powershell
git add backend/ai/client.py backend/tests/test_ai_outreach.py
git commit -m "fix: make OpenCode structured responses reliable"
git push origin main
```

---

### Task 2: Three sales strategies and strict grounded validation

**Files:**
- Modify: `backend/ai/prompts.py`
- Modify: `backend/ai/outreach.py`
- Test: `backend/tests/test_ai_outreach.py`

**Interfaces:**
- Consumes: `AiClient.complete_json(..., validate=...)`.
- Produces: normalized variants shaped as
  `{"tone": str, "title": str, "angle": str, "text": str}` and
  `build_input(...)[“prompt_version”] == 2`.

- [ ] **Step 1: Add failing prompt and validator tests**

Replace the test fixture with the new contract:

```python
GOOD_ANSWER = {
    "analysis": {
        "signal": "Рейтинг 5,0 и 110 отзывов",
        "problem": "В карточке не указан сайт",
        "opportunity": "Упростить путь до обращения",
    },
    "variants": [
        {"tone": "confident", "title": "Уверенный продавец", "text": CONFIDENT_TEXT},
        {"tone": "hard_sell", "title": "Жёсткая продажа", "text": HARD_SELL_TEXT},
        {"tone": "expert", "title": "Эксперт", "text": EXPERT_TEXT},
    ],
    "follow_up": FOLLOW_UP,
}
```

Use 180–320-character fixture messages and add tests for:

```python
self.assertEqual(
    ["confident", "hard_sell", "expert"],
    [item["tone"] for item in result["variants"]],
)
self.assertEqual("Уверенный продавец", result["variants"][0]["title"])
self.assertEqual(2, outreach.build_input(CLIENT, get_profile())["prompt_version"])
```

Assert missing/duplicate tones, messages shorter than 180, messages longer than
320 and messages without a question mark raise `AiError`. Assert a legacy
three-item payload using only `angle` is mapped by position and remains readable.
Assert the prompt contains `не вижу сайта в карточке`, all three tone IDs and
the 180–320 limit.

- [ ] **Step 2: Run the outreach tests and confirm RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_outreach -v
```

Expected: the new tone, prompt-version and strict-validation assertions fail.

- [ ] **Step 3: Replace the prompt contract**

In `prompts.py`, keep the niche economics but replace the long generic
copywriting rules with:

```python
MESSAGE_MIN_LENGTH = 180
MESSAGE_MAX_LENGTH = 320

TONE_INSTRUCTIONS = """
confident — уверенный продавец: конкретно, коммерчески, без давления.
hard_sell — жёсткая продажа: контраст и цена бездействия, но без угроз,
ложного дефицита и выдуманных потерь.
expert — эксперт: сначала диагноз по фактам, затем полезный следующий шаг.
"""
```

The JSON example must use `analysis.signal/problem/opportunity` and exactly the
three `tone` identifiers. The grounding rules must require conditional language
for estimates and the exact safer wording when no website is present.

- [ ] **Step 4: Implement strict normalization**

In `outreach.py`, define:

```python
PROMPT_VERSION = 2
TONE_ORDER = ("confident", "hard_sell", "expert")
TONE_TITLES = {
    "confident": "Уверенный продавец",
    "hard_sell": "Жёсткая продажа",
    "expert": "Эксперт",
}
MIN_LENGTH = 180
MAX_LENGTH = 320
```

Normalize legacy variants by index, require every tone exactly once, preserve
`angle` as the display title for API compatibility, and reject rather than
truncate out-of-range messages. Add `prompt_version` to `build_input`.

Call:

```python
raw = engine.complete_json(
    SYSTEM_PROMPT,
    build_client_message_prompt(client, profile),
    temperature=0.55,
    max_tokens=1800,
    validate=lambda payload: _validate(payload),
)
```

Normalize `analysis` from either the new object or the legacy string and retain
top-level `pain` and `money_argument` compatibility fields.

- [ ] **Step 5: Run the outreach tests and confirm GREEN**

Run the same unittest command. Expected: all outreach tests pass.

- [ ] **Step 6: Commit and push**

```powershell
git add backend/ai/prompts.py backend/ai/outreach.py backend/tests/test_ai_outreach.py
git commit -m "feat: generate three grounded sales approaches"
git push origin main
```

---

### Task 3: Desktop sales workspace modal

**Files:**
- Modify: `src/pages/ClientMessageModal.tsx`
- Create: `src/pages/ClientMessageModal.css`
- Modify: `src/pages/ClientMessageModal.test.tsx`
- Modify: `src/styles.css`

**Interfaces:**
- Consumes: variants with optional `tone`, `title`, legacy `angle`, editable
  `text`; structured or legacy analysis.
- Produces: accessible tabs, selected editable message, compact insight cards,
  sticky actions and retryable errors.

- [ ] **Step 1: Add failing component tests**

Update `GENERATED` to use the new schema and assert:

```tsx
expect(within(dialog).getByRole('tab', { name: /Уверенный продавец/ })).toHaveAttribute('aria-selected', 'true')
expect(within(dialog).getByRole('tab', { name: /Жёсткая продажа/ })).toBeInTheDocument()
expect(within(dialog).getByRole('tab', { name: /Эксперт/ })).toBeInTheDocument()
expect(within(dialog).getByText('Сильный сигнал')).toBeInTheDocument()
expect(within(dialog).getByText('Гипотеза')).toBeInTheDocument()
expect(within(dialog).getByText('Возможность')).toBeInTheDocument()
```

Add a test which edits `confident`, switches to `expert`, edits it, switches
back and expects both edits to remain isolated. Add an error test which expects
a `Повторить` button and verifies another POST. Keep the WhatsApp selected-text
test and one legacy `angle` payload test.

- [ ] **Step 2: Run the component test and confirm RED**

Run:

```powershell
npm.cmd run test:frontend -- src/pages/ClientMessageModal.test.tsx --reporter=dot
```

Expected: missing tone labels, insight cards and retry action.

- [ ] **Step 3: Refactor the component**

Import the new stylesheet:

```tsx
import './ClientMessageModal.css'
```

Normalize labels without mutating the API response:

```tsx
const TONE_META = {
  confident: { title: 'Уверенный продавец', note: 'Прямо и по делу' },
  hard_sell: { title: 'Жёсткая продажа', note: 'Сильнее через цену бездействия' },
  expert: { title: 'Эксперт', note: 'Спокойно через диагностику' },
} as const
```

Build the dialog as:

```tsx
<header className="ai-workspace-header">...</header>
<div className="ai-workspace-grid">
  <aside className="ai-insight-column">...</aside>
  <main className="ai-compose-column">
    <div role="tablist" className="ai-tone-tabs">...</div>
    <textarea className="ai-compose-textarea" ... />
    <details className="ai-follow-up-panel">...</details>
  </main>
</div>
<footer className="ai-workspace-actions">...</footer>
```

Keep drafts in component state. On generation failure, render the error plus a
button that invokes `generate(true)`. Messenger URLs must continue using the
currently selected edited text.

- [ ] **Step 4: Add desktop and theme styles**

Create `ClientMessageModal.css` with these layout constraints:

```css
.client-message-modal {
  width: min(960px, calc(100vw - 48px));
  max-height: calc(100vh - 48px);
  padding: 0;
  overflow: hidden;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.ai-workspace-grid {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(250px, 0.8fr) minmax(420px, 1.4fr);
  overflow: auto;
}

.ai-workspace-actions {
  position: sticky;
  bottom: 0;
}
```

Add visible `:focus-visible`, active, hover, busy and error states, plus
`.theme-dark` overrides. Remove the old `.client-message-modal`,
`.ai-analysis`, `.ai-variant-tabs`, `.ai-message-text`, `.ai-send-row`,
`.ai-follow-up` and `.ai-modal-footer` blocks from `styles.css` so there is one
owner for the component.

- [ ] **Step 5: Run the component tests and confirm GREEN**

Run the same Vitest command. Expected: all modal tests pass.

- [ ] **Step 6: Commit and push**

```powershell
git add src/pages/ClientMessageModal.tsx src/pages/ClientMessageModal.css src/pages/ClientMessageModal.test.tsx src/styles.css
git commit -m "feat: redesign AI sales message workspace"
git push origin main
```

---

### Task 4: Live integration, documentation and full verification

**Files:**
- Modify: `README.md`
- Modify if live evidence requires a regression fix:
  `backend/ai/client.py`, `backend/ai/prompts.py`, `backend/ai/outreach.py`,
  `src/pages/ClientMessageModal.tsx`, `src/pages/ClientMessageModal.css`
- Test corresponding modified source files.

**Interfaces:**
- Consumes: running backend on `127.0.0.1:8000`, frontend on
  `127.0.0.1:5173`, saved OpenCode Go key, client IDs `98` and `28`.
- Produces: verified real results, browser-checked UI and documented behavior.

- [ ] **Step 1: Restart the backend and run real generations**

Call the protected endpoint for both clients:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/ai/clients/98/message?force=true' -Method Post -Headers @{ 'X-Requested-With' = 'SemixCRM' } -ContentType 'application/json' -Body '{}'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/ai/clients/28/message?force=true' -Method Post -Headers @{ 'X-Requested-With' = 'SemixCRM' } -ContentType 'application/json' -Body '{}'
```

For each response, verify exactly three tones, 180–320 characters, a question
in each message, no links, no invented facts and no unqualified revenue promise.

- [ ] **Step 2: Add a regression test for any live-only failure**

If either live request exposes a new deterministic failure, first add the
smallest failing unittest or Vitest case, run it RED, implement one root-cause
fix, then run it GREEN. Do not alter requirements to accept a weak result.

- [ ] **Step 3: Browser-check the desktop dialog**

At `http://127.0.0.1:5173/`, open the client section and generate for
`ЕвроДент`. Verify:

- all three tone tabs switch correctly;
- the message editor and primary actions are visible;
- only the content area scrolls when needed;
- copying and WhatsApp use the selected edited message;
- regenerate shows a busy state and replaces all three variants;
- light and dark themes have no contrast or console errors.

- [ ] **Step 4: Update the README**

Document that the client message assistant returns the three named strategies,
uses structured JSON, disables MiMo thinking for this task, validates every
variant and caches only accepted output.

- [ ] **Step 5: Run fresh full verification**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests
npm.cmd run test:frontend -- --reporter=dot
npm.cmd run build
git diff --check
```

Expected: backend suite OK, all frontend test files pass, TypeScript/Vite build
exits 0 and `git diff --check` reports no errors.

- [ ] **Step 6: Commit, push and compare SHAs**

```powershell
git add -A
git commit -m "docs: explain AI outreach workflow"
git push origin main
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
git status -sb
```

Expected: local and remote SHAs are identical and the worktree is clean.
