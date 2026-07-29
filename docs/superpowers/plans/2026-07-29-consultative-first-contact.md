# Consultative First Contact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить длинные коммерческие первые сообщения тремя короткими диагностическими вопросами и показать в CRM правильную последовательность дальнейшего диалога.

**Architecture:** Существующий JSON-контракт с тремя `variants` сохраняется, но системный промпт и валидатор вводят новую консультативную семантику. Frontend больше не добавляет портфолио и отображает компактный редактор первого вопроса вместе со статической картой этапов 2–7.

**Tech Stack:** Python 3.13, FastAPI, SQLite, OpenAI-compatible API, React, TypeScript, Vitest, unittest.

## Global Constraints

- Первый контакт содержит от 70 до 260 символов.
- В каждом варианте ровно один вопросительный знак, и сообщение заканчивается вопросом.
- Первый контакт не содержит URL, портфолио, цены, рублей, демо, созвона или предложения сайта.
- Контекст берётся только из карточки клиента, ручного наблюдения или подтверждённых отзывов 2GIS.
- Старый API-контракт и профиль исполнителя остаются совместимыми.
- Прежний кэш инвалидируется увеличением `PROMPT_VERSION` с `6` до `7`.

---

### Task 1: Новый AI-контракт и серверная защита

**Files:**
- Modify: `backend/ai/prompts.py`
- Modify: `backend/ai/outreach.py`
- Modify: `backend/tests/test_ai_outreach.py`

**Interfaces:**
- Consumes: `build_client_message_prompt(client, profile, manual_observation, review_evidence) -> str`.
- Produces: три `variants` с тонами `confident`, `hard_sell`, `expert`, длиной 70–260 символов и ровно одним финальным вопросом.

- [x] **Step 1: Replace the shared test fixture with valid diagnostic questions**

```python
GOOD_ANSWER["variants"] = [
    {
        "tone": "confident",
        "title": "Цены и информация",
        "text": (
            "Здравствуйте! Увидел, что в карточке 2GIS не указан отдельный сайт "
            "с услугами и ценами. Пациенты уточняют стоимость у администратора "
            "или у вас есть отдельный прайс?"
        ),
    },
    {
        "tone": "hard_sell",
        "title": "Запись и заявки",
        "text": (
            "Здравствуйте! В карточке 7R вижу телефон и Telegram, но не вижу "
            "онлайн-записи. Пациенты записываются сообщением администратору "
            "или через другую систему?"
        ),
    },
    {
        "tone": "expert",
        "title": "Обработка обращений",
        "text": (
            "Здравствуйте! У 7R высокий рейтинг и 200 отзывов, а из быстрых "
            "контактов вижу Telegram. Кто отвечает пациентам, если они пишут "
            "вечером или администратор занят?"
        ),
    },
]
```

- [x] **Step 2: Add failing prompt and validator tests**

```python
def test_prompt_requires_consultative_first_contact(self) -> None:
    self.assertIn("ровно один вопросительный знак", SYSTEM_PROMPT)
    self.assertIn("70–260 символов", SYSTEM_PROMPT)
    self.assertIn("не предлагай сайт", SYSTEM_PROMPT)
    self.assertIn("Цены и информация", SYSTEM_PROMPT)
    self.assertIn("Запись и заявки", SYSTEM_PROMPT)
    self.assertIn("Обработка обращений", SYSTEM_PROMPT)


def test_rejects_commercial_pitch_in_first_contact(self) -> None:
    variants = [dict(item) for item in GOOD_ANSWER["variants"]]
    variants[0] = {
        **variants[0],
        "text": "Здравствуйте! Предлагаю сделать сайт за 35 000 ₽. Обсудим?",
    }
    transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

    result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

    self.assertEqual(2, len(transport.requests))
    self.assertEqual("Цены и информация", result["variants"][0]["title"])


def test_rejects_two_questions_in_first_contact(self) -> None:
    variants = [dict(item) for item in GOOD_ANSWER["variants"]]
    variants[1] = {
        **variants[1],
        "text": "Здравствуйте! Как сейчас записываются пациенты? Есть отдельная система?",
    }
    transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

    outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

    self.assertEqual(2, len(transport.requests))
```

- [x] **Step 3: Run the targeted backend tests and verify RED**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_ai_outreach.PromptTests.test_prompt_requires_consultative_first_contact `
  backend.tests.test_ai_outreach.GenerationTests.test_rejects_commercial_pitch_in_first_contact `
  backend.tests.test_ai_outreach.GenerationTests.test_rejects_two_questions_in_first_contact
```

Expected: FAIL because the prompt, titles, length rules and commercial-content checks still describe the old long pitch.

- [x] **Step 4: Implement the prompt and validation contract**

In `backend/ai/prompts.py`:

```python
MESSAGE_MIN_LENGTH = 70
MESSAGE_MAX_LENGTH = 260
TONE_LENGTHS = {
    "confident": (70, 260),
    "hard_sell": (70, 260),
    "expert": (70, 260),
}
```

Replace `SYSTEM_PROMPT` with rules that require context plus one process question,
the titles `Цены и информация`, `Запись и заявки`, `Обработка обращений`, and forbid
solutions, links, portfolio, prices, demos and calls. Remove the economics and full
executor-profile blocks from `build_client_message_prompt`; include only
`Имя отправителя: {profile.sender_name}` to prevent addressing the client by that name.

In `backend/ai/outreach.py`:

```python
PROMPT_VERSION = 7
TONE_TITLES = {
    "confident": "Цены и информация",
    "hard_sell": "Запись и заявки",
    "expert": "Обработка обращений",
}
COMMERCIAL_FIRST_CONTACT = re.compile(
    r"https?://|www\.|портфолио|(?:\\d[\\d\\s]*)?\\s*(?:₽|руб(?:\\.|л|лей)?)|"
    r"демо|прототип|созвон|предлагаю\\s+(?:сотрудничество|сделать|разработать)|"
    r"(?:сделаю|разработаю|соберу)\\s+(?:для\\s+вас\\s+)?сайт|"
    r"пришлю\\s+(?:варианты|стоимость|сроки|презентацию)",
    re.IGNORECASE,
)
```

The replacement prompt must contain this complete contract:

```python
SYSTEM_PROMPT = """Ты — консультативный B2B-продавец для малого бизнеса в России.
Ты пишешь только первое холодное сообщение владельцу в WhatsApp или Telegram.
Цель первого сообщения — не продать сайт, а получить честный короткий ответ о том,
как сейчас устроен один конкретный процесс.

ФОРМУЛА
Конкретный проверенный контекст + один вопрос о текущем процессе + лёгкий ответ.
— 70–260 символов.
— Одна или две короткие фразы после приветствия.
— Ровно один вопросительный знак; сообщение заканчивается вопросом.
— Вопрос должен быть таким, чтобы на него можно было ответить фактом или одной фразой.
— Не притворяйся клиентом и не скрывай деловую цель вымышленной историей.

ТРИ ДИАГНОСТИЧЕСКИХ УГЛА
confident — «Цены и информация»: как клиент узнаёт цены, услуги или детали.
hard_sell — «Запись и заявки»: как клиент записывается и куда поступает заявка.
expert — «Обработка обращений»: что происходит вечером, при пропущенном звонке
или когда администратор не успевает ответить.

ДОКАЗАТЕЛЬСТВА
— Используй только карточку, ручное наблюдение и переданные отзывы 2GIS.
— review_insight.evidence_ids содержит только переданные R1, R2 и так далее.
— Без отзывов нельзя писать, что ты их читал, или приписывать клиентам похвалу.
— Если сайт не указан, пиши «в карточке 2GIS не увидел отдельного сайта».
— Не объявляй потерю клиентов фактом и не выдумывай текущий процесс.

В ПЕРВОМ СООБЩЕНИИ ЗАПРЕЩЕНО
— Предлагать сайт, автоматизацию, сотрудничество или другую услугу.
— URL, портфолио, цена, рубли, сроки, демо, прототип, презентация или созвон.
— «Актуально?», «Интересно?», «Хотите?», ответ «да» и рекламные штампы.
— Несколько вопросов, сложный выбор или вопрос о покупке.

Верни ТОЛЬКО JSON:
{
  "analysis": {
    "signal": "проверенный контекст",
    "problem": "процесс, который стоит уточнить",
    "opportunity": "почему ответ поможет продолжить диагностику"
  },
  "review_insight": {
    "summary": "деталь из отзывов или пустая строка",
    "evidence_ids": ["R1"]
  },
  "variants": [
    {"tone": "confident", "title": "Цены и информация", "text": "70–260 символов"},
    {"tone": "hard_sell", "title": "Запись и заявки", "text": "70–260 символов"},
    {"tone": "expert", "title": "Обработка обращений", "text": "70–260 символов"}
  ],
  "follow_up": ""
}"""
```

Before cleaning each variant, reject `COMMERCIAL_FIRST_CONTACT` in the raw text.
Remove the `_strengthen_final_question` and `_compact_message` calls from validation.
Reject unless:

```python
if text.count("?") != 1 or not text.endswith("?"):
    raise AiError("Первое сообщение должно содержать ровно один вопрос и заканчиваться им")
```

- [x] **Step 5: Run the AI regression suite**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_outreach
```

Expected: all tests pass after updating old long-message assertions to the new contract.

- [x] **Step 6: Commit and push Task 1**

```powershell
git add backend/ai/prompts.py backend/ai/outreach.py backend/tests/test_ai_outreach.py
git commit -m "feat: generate consultative first-contact questions"
git push origin main
```

---

### Task 2: Диагностический интерфейс и карта разговора

**Files:**
- Modify: `src/pages/ClientMessageModal.tsx`
- Modify: `src/pages/ClientMessageModal.css`
- Modify: `src/pages/ClientMessageModal.test.tsx`

**Interfaces:**
- Consumes: совместимый `ClientMessage` с тремя короткими `variants`.
- Produces: редактор диагностического вопроса без портфолио и сворачиваемую карту этапов после ответа.

- [x] **Step 1: Replace the frontend fixture with short diagnostic variants**

```ts
variants: [
  { tone: 'confident', title: 'Цены и информация', text: 'Здравствуйте! В карточке 2GIS не увидел отдельного сайта с услугами и ценами. Клиенты уточняют стоимость у администратора или есть отдельный прайс?' },
  { tone: 'hard_sell', title: 'Запись и заявки', text: 'Здравствуйте! В карточке вижу телефон и Telegram, но не вижу онлайн-записи. Клиенты записываются сообщением администратору или через другую систему?' },
  { tone: 'expert', title: 'Обработка обращений', text: 'Здравствуйте! У 7R высокий рейтинг и 200 отзывов. Кто отвечает пациентам, если они пишут вечером или администратор занят?' },
],
```

- [x] **Step 2: Add failing UI tests**

```tsx
it('не добавляет портфолио в первое диагностическое сообщение', async () => {
  vi.stubGlobal('fetch', createFetchMock({ cached: true }))
  renderModal()

  const editor = await screen.findByLabelText('Первый диагностический вопрос')
  expect((editor as HTMLTextAreaElement).value).not.toContain('http')
  expect(screen.queryByRole('checkbox', { name: 'Добавлять портфолио в тексты' })).not.toBeInTheDocument()
})

it('показывает три диагностических угла и карту следующих этапов', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', createFetchMock({ cached: true }))
  renderModal()

  expect(await screen.findByRole('tab', { name: /Цены и информация/ })).toBeVisible()
  expect(screen.getByRole('tab', { name: /Запись и заявки/ })).toBeVisible()
  expect(screen.getByRole('tab', { name: /Обработка обращений/ })).toBeVisible()

  await user.click(screen.getByText('Что делать после ответа'))
  expect(screen.getByText('Найти слабое место')).toBeVisible()
  expect(screen.getByText('Показать решение')).toBeVisible()
  expect(screen.getByText('Предложить следующий шаг')).toBeVisible()
})
```

- [x] **Step 3: Run the modal tests and verify RED**

Run:

```powershell
npm.cmd run test:frontend -- src/pages/ClientMessageModal.test.tsx
```

Expected: FAIL because the old portfolio switch and old commercial labels are still present.

- [x] **Step 4: Implement the diagnostic workspace**

In `ClientMessageModal.tsx`:

```ts
const TONE_META = {
  confident: { title: 'Цены и информация', note: 'Как клиент узнаёт нужные детали' },
  hard_sell: { title: 'Запись и заявки', note: 'Как устроен путь до обращения' },
  expert: { title: 'Обработка обращений', note: 'Что происходит, когда сразу ответить не могут' },
} satisfies Record<MessageTone, { title: string; note: string }>

const TONE_LENGTHS = {
  confident: [70, 260],
  hard_sell: [70, 260],
  expert: [70, 260],
} satisfies Record<MessageTone, [number, number]>

const CONVERSATION_STAGES = [
  { step: 2, title: 'Найти слабое место', note: 'Уточнить, что происходит, когда текущий процесс не срабатывает.' },
  { step: 3, title: 'Помочь увидеть последствия', note: 'Проверить вместе, может ли из-за этого потеряться обращение.' },
  { step: 4, title: 'Уточнить желаемый результат', note: 'Спросить, какой процесс был бы удобнее для бизнеса.' },
  { step: 5, title: 'Показать решение', note: 'Только после подтверждения проблемы показать подходящее решение.' },
  { step: 6, title: 'Подтвердить компетентность', note: 'Здесь уже уместны портфолио, кейсы и короткое представление.' },
  { step: 7, title: 'Предложить следующий шаг', note: 'Предложить конкретное время короткого показа или обсуждения.' },
]
```

Delete portfolio helpers, `includePortfolio`, both portfolio checkboxes and all calls
to `applyPortfolio`. Render the API message unchanged. Change the heading to
`Первое диагностическое сообщение`, the action to `Сгенерировать 3 вопроса`, the editor
label to `Первый диагностический вопрос`, and `rows` to `5`. Replace the old three-day
follow-up with `<details>` that renders `CONVERSATION_STAGES`.

Add focused CSS for `.ai-conversation-map`, `.ai-conversation-stage` and the compact
textarea while preserving desktop scrolling, focus visibility and dark mode.

```css
.ai-compose-textarea {
  min-height: 140px;
}

.ai-conversation-map {
  border: 1px solid #dfe5ee;
  border-radius: 14px;
  background: #f8fafc;
  overflow: hidden;
}

.ai-conversation-map > summary {
  cursor: pointer;
  padding: 14px 16px;
  font-weight: 700;
}

.ai-conversation-stages {
  display: grid;
  gap: 8px;
  padding: 0 16px 16px;
}

.ai-conversation-stage {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 10px;
  padding: 10px;
  border-radius: 10px;
  background: #fff;
}
```

- [x] **Step 5: Run frontend tests and build**

Run:

```powershell
npm.cmd run test:frontend
npm.cmd run build
```

Expected: all frontend tests pass and Vite production build exits with code 0.

- [ ] **Step 6: Commit and push Task 2**

```powershell
git add src/pages/ClientMessageModal.tsx src/pages/ClientMessageModal.css src/pages/ClientMessageModal.test.tsx
git commit -m "feat: add consultative outreach workspace"
git push origin main
```

---

### Task 3: Документация и сквозная проверка

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-29-consultative-first-contact.md`

**Interfaces:**
- Consumes: готовый backend и frontend из Tasks 1–2.
- Produces: актуальная инструкция и подтверждённый живой результат.

- [ ] **Step 1: Update README**

Replace the old AI description with:

```md
Первое касание строится как короткий диагностический вопрос: проверенный контекст
из карточки или отзывов 2GIS и один вопрос о текущем процессе. В нём нет ссылки,
портфолио, цены или предложения сайта. Портфолио показывается только после того,
как клиент подтвердил проблему.

Под редактором находится карта следующих этапов консультативного диалога:
слабое место → последствия → желаемый результат → решение → компетентность →
следующий шаг.
```

- [ ] **Step 2: Run full verification**

Run:

```powershell
npm.cmd run test:frontend
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests
npm.cmd run build
git diff --check
```

Expected: 0 failed tests, build exit code 0 and no whitespace errors.

- [ ] **Step 3: Verify a real 2GIS client**

Restart the local backend if it is not using `PROMPT_VERSION = 7`. Generate a forced
message for a real client such as Cosmo, then verify all three texts:

```text
70 <= length <= 260
question_mark_count == 1
ends_with_question == true
contains_url_or_price_or_offer == false
```

Open the saved result in the CRM and confirm the three diagnostic tabs, compact editor,
absence of the portfolio switch and the expanded conversation map.

- [ ] **Step 4: Commit and push documentation**

```powershell
git add README.md docs/superpowers/plans/2026-07-29-consultative-first-contact.md
git commit -m "docs: explain consultative outreach workflow"
git push origin main
```
