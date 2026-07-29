# Source-Neutral First Contact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать из первого сообщения любые упоминания 2GIS, карточки, отзывов и способа поиска компании, сохранив персональный вопрос о текущем процессе.

**Architecture:** AI продолжает получать внутренние данные клиента и отзывы, но системный промпт запрещает раскрывать источник. Backend проверяет сырой текст регулярным выражением, а `PROMPT_VERSION = 8` делает старые сообщения неактуальными.

**Tech Stack:** Python 3.13, FastAPI, OpenAI-compatible API, React, TypeScript, unittest, Vitest.

## Global Constraints

- Первое сообщение содержит 70–260 символов и ровно один финальный вопрос.
- Сообщение начинается нейтрально и спрашивает, как сейчас устроен конкретный процесс.
- В сообщении нет `2GIS`, `2ГИС`, карточки, отзывов или объяснения, где найдена компания.
- В сообщении нет ссылки, портфолио, цены, демо, созвона или предложения услуги.
- Внутренние данные 2GIS и отзывы остаются доступны AI для выбора релевантной услуги или процесса.

---

### Task 1: Серверный контракт без раскрытия источника

**Files:**
- Modify: `backend/tests/test_ai_outreach.py`
- Modify: `backend/ai/prompts.py`
- Modify: `backend/ai/outreach.py`

**Interfaces:**
- Consumes: `generate_client_message(client, force, manual_observation, ai_client, review_loader)`.
- Produces: три source-neutral `variants`; `PROMPT_VERSION = 8`.

- [x] **Step 1: Replace the valid fixtures**

Заменить тексты `GOOD_ANSWER` на вопросы без указания источника:

```python
"Здравствуйте! Подскажите, пожалуйста, как у вас сейчас клиенты узнают цены "
"на процедуры: есть отдельный онлайн-прайс или всё уточняют у администратора?"
```

Остальные углы аналогично спрашивают о записи и обработке вечерних обращений.
`REVIEW_ANSWER` использует подтверждённую услугу или специалиста, но не говорит,
что деталь взята из отзывов.

- [x] **Step 2: Write failing prompt and validation tests**

```python
def test_prompt_forbids_disclosing_lead_source(self) -> None:
    self.assertIn("не упоминай 2GIS", SYSTEM_PROMPT)
    self.assertIn("не упоминай карточку", SYSTEM_PROMPT)
    self.assertIn("не упоминай отзывы", SYSTEM_PROMPT)
    self.assertNotIn("в карточке 2GIS не увидел отдельного сайта", SYSTEM_PROMPT)


def test_source_disclosure_triggers_one_repair(self) -> None:
    invalid = {
        **GOOD_ANSWER,
        "variants": [
            {
                **GOOD_ANSWER["variants"][0],
                "text": (
                    "Здравствуйте! В карточке 2GIS не увидел отдельного прайса. "
                    "Клиенты уточняют цены у администратора или есть другой способ?"
                ),
            },
            *GOOD_ANSWER["variants"][1:],
        ],
    }
    transport = RecordingTransport(invalid, GOOD_ANSWER)

    outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

    self.assertEqual(2, len(transport.calls))
```

- [x] **Step 3: Run the new tests and verify RED**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_ai_outreach.PromptTests.test_prompt_forbids_disclosing_lead_source `
  backend.tests.test_ai_outreach.GenerationTests.test_source_disclosure_triggers_one_repair
```

Expected: FAIL because the old prompt recommends “в карточке 2GIS”, and the validator
does not reject source disclosure.

- [x] **Step 4: Implement the prompt and validator**

In `backend/ai/prompts.py`, teach the model to ask directly about the process:

```text
Не объясняй, где найдена компания.
Не упоминай 2GIS, карточку, отзывы, поиск компании или источник лида.
Начинай естественно: «Здравствуйте! Подскажите, пожалуйста, как у вас сейчас…»
```

Replace the example questions with source-neutral questions. In
`backend/ai/outreach.py`:

```python
PROMPT_VERSION = 8
SOURCE_DISCLOSURE = re.compile(
    r"\b2\s*(?:gis|гис)\b|\bдвухгис\w*\b|\bкарточк\w*\b|\bотзыв\w*\b|"
    r"\b(?:наш[её]л|увидел)\s+(?:вас|вашу\s+компани\w*)\b",
    re.IGNORECASE,
)
```

Reject `SOURCE_DISCLOSURE` in the raw variant before cleaning.

- [x] **Step 5: Run the AI regression suite**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.tests.test_ai_outreach
```

Expected: all tests pass.

---

### Task 2: Примеры в интерфейсе и документации

**Files:**
- Modify: `src/pages/ClientMessageModal.test.tsx`
- Modify: `README.md`

**Interfaces:**
- Consumes: unchanged `ClientMessage` JSON.
- Produces: source-neutral UI fixtures and current README behavior.

- [x] **Step 1: Replace frontend fixture messages**

Use the same three direct process questions as backend fixtures. Keep the existing
tests for three tabs, draft editing, WhatsApp encoding and absence of portfolio.

- [x] **Step 2: Update README**

Document that 2GIS and reviews are internal sources only. The first message does not
say where the company was found and instead asks directly about prices, booking or
request handling.

- [x] **Step 3: Run frontend tests and build**

Run:

```powershell
npm.cmd run test:frontend
npm.cmd run build
```

Expected: 75 tests pass and build exits with code 0.

---

### Task 3: Live verification and delivery

**Files:**
- Modify: `docs/superpowers/plans/2026-07-29-source-neutral-first-contact.md`

**Interfaces:**
- Consumes: completed backend and frontend.
- Produces: verified live Cosmo result and pushed `main`.

- [x] **Step 1: Restart backend and generate Cosmo**

Force-generate client `139`, then assert for each variant:

```text
70 <= length <= 260
question_count == 1
ends_with_question == true
does_not_match == 2GIS|2ГИС|карточк|отзыв|нашёл вас|увидел вас
```

- [x] **Step 2: Run full regression**

```powershell
npm.cmd run test:frontend
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests
npm.cmd run build
git diff --check
```

- [ ] **Step 3: Commit and push**

```powershell
git add backend/ai/prompts.py backend/ai/outreach.py backend/tests/test_ai_outreach.py `
  src/pages/ClientMessageModal.test.tsx README.md `
  docs/superpowers/plans/2026-07-29-source-neutral-first-contact.md
git commit -m "fix: hide lead source from first contact"
git push origin main
```
