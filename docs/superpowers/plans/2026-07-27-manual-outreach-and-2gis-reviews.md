# Manual AI Outreach and 2GIS Reviews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make client-message generation explicitly user-triggered, visible on client cards, grounded in real 2GIS review evidence, and able to add or remove the configured portfolio link locally.

**Architecture:** Add a focused 2GIS review-evidence adapter that reads the server-rendered React Query state, then pass bounded numbered excerpts into the existing structured OpenCode Go request. Extend AI storage with one batched status query, keep generation and cached reads separate, and let the React dialog own the deterministic portfolio paragraph so toggling it never calls the model.

**Tech Stack:** Python 3.13, FastAPI, SQLite, httpx, BeautifulSoup, unittest, React 19, TypeScript, Vitest, Testing Library, CSS.

## Global Constraints

- Opening `Посмотреть текст` must issue no POST request.
- Review-specific claims must cite identifiers from real reviews of the same 2GIS card.
- Review retrieval failure must not block message generation.
- The primary text follows the approved 650–1,100 character structure.
- The portfolio URL defaults to `https://semyon-lobanov-portfolio.vercel.app/` and is removable without regeneration.
- Personal demo sites and automatic message sending remain out of scope.
- No dedicated mobile redesign is required.

---

### Task 1: Extract bounded review evidence from 2GIS

**Files:**
- Create: `backend/ai/reviews.py`
- Create: `backend/tests/fixtures/ai/2gis_reviews_page.html`
- Create: `backend/tests/test_ai_reviews.py`

**Interfaces:**
- Produces: `fetch_2gis_review_evidence(card_url: str, *, transport: httpx.BaseTransport | None = None) -> list[dict[str, str]]`
- Each item is `{"id": "R1", "text": "bounded public review text"}`.
- Invalid/non-2GIS URLs return an empty list without network access.

- [ ] **Step 1: Add the failing extraction tests**

```python
class ReviewEvidenceTests(unittest.TestCase):
    def test_extracts_numbered_customer_reviews_from_react_query_state(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, text=FIXTURE.read_text(encoding="utf-8")
        ))
        result = fetch_2gis_review_evidence(
            "https://2gis.ru/firm/70000001042303479", transport=transport
        )
        self.assertEqual(["R1", "R2", "R3"], [item["id"] for item in result])
        self.assertIn("косметолог Анна", result[1]["text"])

    def test_rejects_untrusted_url_without_request(self):
        calls = []
        transport = httpx.MockTransport(lambda request: calls.append(request))
        self.assertEqual([], fetch_2gis_review_evidence(
            "https://example.com/firm/1", transport=transport
        ))
        self.assertEqual([], calls)

    def test_network_failure_returns_empty_evidence(self):
        transport = httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(httpx.ConnectError("offline"))
        )
        self.assertEqual([], fetch_2gis_review_evidence(
            "https://2gis.ru/firm/1", transport=transport
        ))
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_reviews -v
```

Expected: import failure because `backend.ai.reviews` does not exist.

- [ ] **Step 3: Implement the adapter**

```python
FIRM_URL = re.compile(r"^https://(?:www\.)?2gis\.ru/(?:[^/]+/)?firm/(\d+)(?:/|$)")
STATE = re.compile(
    r"var __REACT_QUERY_STATE__ = JSON\.parse\('((?:\\.|[^'])*)'\);",
    re.DOTALL,
)

def fetch_2gis_review_evidence(card_url, *, transport=None):
    match = FIRM_URL.match(str(card_url or "").strip())
    if not match:
        return []
    url = f"https://2gis.ru/firm/{match.group(1)}/tab/reviews"
    try:
        with httpx.Client(
            transport=transport, follow_redirects=True, timeout=8,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
        if len(response.content) > 2_000_000:
            return []
        script = next(
            node.get_text()
            for node in BeautifulSoup(response.text, "html.parser").find_all("script")
            if "fetchEntityReviews" in node.get_text()
        )
        encoded = STATE.search(script)
        state = json.loads(ast.literal_eval("'" + encoded.group(1) + "'"))
    except (StopIteration, AttributeError, ValueError, SyntaxError, httpx.HTTPError):
        return []
    texts = []
    for query in state.get("queries", []):
        if (query.get("queryKey") or [None])[0] != "fetchEntityReviews":
            continue
        for page in query.get("state", {}).get("data", {}).get("pages", []):
            for item in page.get("items", []):
                text = clean_review_text(item.get("text"))
                if text and text not in texts:
                    texts.append(text)
    return [{"id": f"R{index}", "text": text} for index, text in enumerate(texts[:7], 1)]
```

`clean_review_text` collapses whitespace, rejects text shorter than 35
characters and clips at 600 characters.

- [ ] **Step 4: Verify GREEN**

Run the Task 1 command. Expected: all review tests pass.

- [ ] **Step 5: Commit and push**

```powershell
git add backend/ai/reviews.py backend/tests/fixtures/ai/2gis_reviews_page.html backend/tests/test_ai_reviews.py
git commit -m "feat: read grounded evidence from 2GIS reviews"
git push origin main
```

### Task 2: Generate the approved long-form strategies

**Files:**
- Modify: `backend/ai/profile.py`
- Modify: `backend/ai/prompts.py`
- Modify: `backend/ai/outreach.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/test_ai_outreach.py`

**Interfaces:**
- `build_input(client, profile, manual_observation="", review_evidence=[])`
- `generate_client_message(client, force=False, manual_observation="", ai_client=None, review_loader=fetch_2gis_review_evidence)`
- POST JSON: `{"manual_observation": "verified optional fact"}`
- Response adds `review_insight`, `review_evidence`, `portfolio_url`.

- [ ] **Step 1: Write failing prompt, validation and API tests**

```python
def test_prompt_contains_numbered_review_evidence_and_manual_observation(self):
    prompt = build_client_message_prompt(
        CLIENT, ExecutorProfile(), "На сайте нет формы записи",
        [{"id": "R1", "text": "Клиенты хвалят внимательного мастера Анну"}],
    )
    self.assertIn("[R1]", prompt)
    self.assertIn("На сайте нет формы записи", prompt)

def test_primary_variant_uses_supported_review_ids(self):
    payload = generated_payload(
        review_insight={"summary": "Хвалят мастера Анну", "evidence_ids": ["R1"]}
    )
    result = outreach.generate_client_message(
        CLIENT,
        ai_client=client_for(payload),
        review_loader=lambda _: [{"id": "R1", "text": "Хвалят мастера Анну"}],
    )
    self.assertEqual(["R1"], result["review_insight"]["evidence_ids"])

def test_generation_without_reviews_never_claims_they_were_read(self):
    with self.assertRaises(AiError):
        outreach._validate(generated_payload(
            review_insight={"summary": "Клиенты хвалят Анну", "evidence_ids": ["R1"]}
        ), "", [])

def test_post_accepts_manual_observation(self):
    response = self.client.post(
        "/api/ai/clients/28/message",
        json={"manual_observation": "На сайте нет формы записи"},
        headers=POWERFUL_HEADERS,
    )
    self.assertEqual(200, response.status_code)
```

- [ ] **Step 2: Run the focused backend tests and verify RED**

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_outreach -v
```

Expected: failures for the new signatures, strategy identifiers and response
fields.

- [ ] **Step 3: Implement the new structured contract**

Set:

```python
PROMPT_VERSION = 6
TONE_ORDER = ("review_growth", "solution", "short")
TONE_LIMITS = {
    "review_growth": (650, 1100),
    "solution": (450, 800),
    "short": (220, 380),
}
```

The prompt instructs the model to return `review_insight.summary`,
`review_insight.evidence_ids`, three paragraphs-based variants and a follow-up.
It explicitly forbids URLs and the claim that the company definitely has no
site. `_validate` checks that every evidence ID is in the supplied evidence
set, enforces per-strategy length bounds and preserves paragraph breaks.

`generate_client_message` calls the review loader once, includes the manual
observation and evidence in the cache fingerprint, and returns:

```python
{
    **result,
    "review_evidence": review_evidence,
    "portfolio_url": profile.portfolio_url,
    "warnings": warnings,
}
```

Update `ExecutorProfile.portfolio_url` to the approved URL. Add:

```python
class AiMessageRequest(BaseModel):
    manual_observation: str = Field(default="", max_length=500)
```

The POST endpoint accepts an optional request body and forwards the trimmed
observation.

- [ ] **Step 4: Verify GREEN**

Run Task 2 tests. Expected: all AI outreach tests pass.

- [ ] **Step 5: Commit and push**

```powershell
git add backend/ai/profile.py backend/ai/prompts.py backend/ai/outreach.py backend/main.py backend/tests/test_ai_outreach.py
git commit -m "feat: generate review-grounded client outreach"
git push origin main
```

### Task 3: Expose message readiness on client rows

**Files:**
- Modify: `backend/ai/storage.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/test_ai_outreach.py`

**Interfaces:**
- `list_result_metadata(task: str, entity_type: str) -> dict[int, dict[str, str]]`
- `GET /api/clients` adds `ai_message_status` and `ai_message_created_at`.

- [ ] **Step 1: Add failing storage/API tests**

```python
def test_client_list_marks_missing_ready_and_stale_messages(self):
    payload = self.client.get("/api/clients").json()
    self.assertEqual("missing", payload["clients"][0]["ai_message_status"])
    generate_for(payload["clients"][0]["id"])
    ready = self.client.get("/api/clients").json()["clients"][0]
    self.assertEqual("ready", ready["ai_message_status"])
    self.assertTrue(ready["ai_message_created_at"])
```

Also save a deliberately different `input_hash` and assert `stale`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_outreach -v
```

Expected: client fields are absent.

- [ ] **Step 3: Implement a single metadata query**

```python
def list_result_metadata(task, entity_type):
    with _connect() as connection:
        rows = connection.execute(
            "SELECT entity_id, input_hash, payload_json, created_at "
            "FROM ai_results WHERE task = ? AND entity_type = ?",
            (task, entity_type),
        ).fetchall()
    return {int(row["entity_id"]): dict(row) for row in rows}
```

`GET /api/clients` loads the executor profile and metadata once. For every
client it reconstructs the current fingerprint using the result's stored
manual observation and review-evidence snapshot. It attaches `missing`,
`ready` or `stale` plus the timestamp without fetching 2GIS reviews.

- [ ] **Step 4: Verify GREEN**

Run Task 3 tests. Expected: status tests pass.

- [ ] **Step 5: Commit and push**

```powershell
git add backend/ai/storage.py backend/main.py backend/tests/test_ai_outreach.py
git commit -m "feat: expose AI draft status for clients"
git push origin main
```

### Task 4: Add manual generation, status badges and portfolio control

**Files:**
- Modify: `src/pages/ClientsPage.tsx`
- Modify: `src/pages/ClientMessageModal.tsx`
- Modify: `src/pages/ClientMessageModal.css`
- Modify: `src/pages/ClientMessageModal.test.tsx`
- Modify: `src/pages/ClientsPage.test.tsx`

**Interfaces:**
- `ClientMessageModal` adds `onGenerated: (createdAt: string) => void`.
- Client fields add `aiMessageStatus` and `aiMessageCreatedAt`.
- Portfolio helpers:
  `addPortfolioBlock(text: string, url: string): string` and
  `removePortfolioBlock(text: string, url: string): string`.

- [ ] **Step 1: Write failing frontend tests**

```tsx
it('does not generate until the user presses the button', async () => {
  const fetchMock = createFetchMock({ ready: false })
  vi.stubGlobal('fetch', fetchMock)
  renderModal()
  await screen.findByRole('button', { name: 'Сгенерировать 3 текста' })
  expect(fetchMock).not.toHaveBeenCalledWith(
    expect.stringContaining('/message'),
    expect.objectContaining({ method: 'POST' }),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Сгенерировать 3 текста' }))
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining('/message'),
    expect.objectContaining({ method: 'POST' }),
  )
})

it('removes and restores the portfolio without another POST', async () => {
  const fetchMock = createFetchMock({ cached: true })
  vi.stubGlobal('fetch', fetchMock)
  renderModal()
  const editor = await screen.findByLabelText('Текст сообщения')
  const toggle = screen.getByRole('checkbox', { name: 'Добавить портфолио' })
  expect(editor).toHaveValue(expect.stringContaining('semyon-lobanov-portfolio.vercel.app'))
  await userEvent.click(toggle)
  expect(editor).not.toHaveValue(expect.stringContaining('semyon-lobanov-portfolio.vercel.app'))
  await userEvent.click(toggle)
  expect(editor).toHaveValue(expect.stringContaining('semyon-lobanov-portfolio.vercel.app'))
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
})

it('shows generated status on the matching client row', async () => {
  render(<ClientsPage />)
  expect(await screen.findByText('Текст готов')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Посмотреть текст/i })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
npm.cmd run test:frontend -- src/pages/ClientMessageModal.test.tsx src/pages/ClientsPage.test.tsx --reporter=dot
```

Expected: auto-generation, missing button and missing badges make the tests fail.

- [ ] **Step 3: Implement the React flow**

The modal `useEffect` performs only GET. The no-result branch renders the manual
observation input, enabled portfolio switch and primary generation button. The
POST sends:

```ts
{
  method: 'POST',
  body: JSON.stringify({ manual_observation: manualObservation.trim() }),
}
```

After a result arrives, build independent editable drafts. Portfolio toggling
adds or removes the exact standard paragraph immediately before the final
paragraph and never resets other edits.

Rename the tabs to:

```ts
{
  review_growth: { title: 'По отзывам и точке роста', note: 'Рекомендуемый' },
  solution: { title: 'Решение и портфолио', note: 'Прямой оффер' },
  short: { title: 'Короткий контакт', note: 'Первое касание' },
}
```

Client rows render a semantic badge and always show `Посмотреть текст`.
`onGenerated` updates only the matching client in local state.

- [ ] **Step 4: Apply the desktop UI rules**

Keep the existing 980px workspace, clear primary-action hierarchy, accessible
switch label, visible keyboard focus, no nested horizontal scroll and readable
light/dark contrast. Use Lucide icons already installed; do not add emoji or a
new icon library.

- [ ] **Step 5: Verify GREEN**

Run Task 4 tests and `npm.cmd run build`. Expected: focused tests and build pass.

- [ ] **Step 6: Commit and push**

```powershell
git add src/pages/ClientsPage.tsx src/pages/ClientMessageModal.tsx src/pages/ClientMessageModal.css src/pages/ClientMessageModal.test.tsx src/pages/ClientsPage.test.tsx
git commit -m "feat: add manual AI outreach workflow"
git push origin main
```

### Task 5: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `src/guides.ts`

**Interfaces:**
- Documentation reflects the exact user-visible flow and fallback behaviour.

- [ ] **Step 1: Update documentation**

Document `Посмотреть текст`, manual generation, 2GIS review evidence, message
statuses, the three new strategies and the removable portfolio block. Remove
the obsolete claim that opening the dialog automatically generates a message.

- [ ] **Step 2: Run complete verification**

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
npm.cmd run test:frontend -- --reporter=dot
npm.cmd run build
git diff --check
```

Expected: every test passes, production build succeeds and diff check is clean.

- [ ] **Step 3: Perform live verification**

In the running desktop browser:

1. Open a never-generated client and confirm no generation starts.
2. Generate for Cosmo and compare `review_insight.evidence_ids` with the
   displayed real review excerpts.
3. Toggle portfolio off and on without another network generation.
4. Confirm row badge changes to `Текст готов`.
5. Confirm copy and WhatsApp contain the visible edited text.
6. Check browser console errors and the 980px layout.

- [ ] **Step 4: Commit, push and compare remote state**

```powershell
git add README.md src/guides.ts
git commit -m "docs: explain review-grounded outreach"
git push origin main
git rev-parse HEAD
git rev-parse origin/main
git status --short
```

Expected: local and remote SHAs match and the worktree is clean.
