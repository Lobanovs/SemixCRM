# Parser2GIS Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать сбор клиентов из 2ГИС рабочим в чистом клоне SemixCRM без внешних каталогов `LeadHunt` и `parser2gic`.

**Architecture:** Новый `backend/parser2gis_runtime.py` управляет отдельным Python-окружением и возвращает CLI-команду официального `interlark/parser-2gis`. `backend/parser.py` отвечает только за параметры запуска, проверку результата и преобразование JSON в лиды.

**Tech Stack:** Python 3.13, `venv`, `subprocess`, `parser-2gis==1.2.1`, unittest, FastAPI, React/Vite.

## Global Constraints

- Upstream-пакет закреплён как `parser-2gis==1.2.1`.
- Pydantic 1.x upstream-парсера не устанавливается в `backend/.venv`.
- `PARSER2GIS_HEADLESS` по умолчанию равен `no`, поскольку headless-запуск вызывает CAPTCHA 2ГИС.
- Существующий сбор Яндекс Карт не меняется.
- Все изменения коммитятся и отправляются в ветку `main` GitHub-репозитория пользователя.

---

### Task 1: Regression Tests

**Files:**
- Modify: `backend/tests/test_parser_start_page.py`
- Create: `backend/tests/test_parser2gis_runtime.py`

**Interfaces:**
- Consumes: `backend.parser.collect_2gis(city, niche, limit, on_status=None, start_page=1)`.
- Produces: ожидаемый интерфейс `ensure_parser2gis_command(on_status=None) -> list[str]`.

- [ ] **Step 1: Write the failing collect test**

Подменить будущий `ensure_parser2gis_command()` на `['parser-2gis']`, записать совместимый JSON в fake subprocess и проверить, что CLI получает URL с `/page/4` без проверок старых внешних каталогов.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_parser_start_page.ParserStartPageTests.test_collect_2gis_passes_selected_page_to_parser_command -v`

Expected: FAIL с `FileNotFoundError` для старого `parser2gic/parse_runner.py`.

- [ ] **Step 3: Write runtime behavior tests**

Проверить три точных сценария: готовый runtime проходит import-probe без pip; отсутствующий пакет вызывает `python -m pip install -r backend/parser2gis-requirements.txt`; `PARSER2GIS_PYTHON` возвращается как начало CLI-команды без создания локального venv.

### Task 2: Isolated Runtime

**Files:**
- Create: `backend/parser2gis_runtime.py`
- Create: `backend/parser2gis-requirements.txt`

**Interfaces:**
- Consumes: `PARSER2GIS_RUNTIME_DIR`, `PARSER2GIS_PYTHON`, optional status callback.
- Produces: `ensure_parser2gis_command(on_status: Callable[[str], None] | None = None) -> list[str]`.

- [ ] **Step 1: Add the pinned dependency manifest**

```text
parser-2gis==1.2.1
```

- [ ] **Step 2: Implement runtime discovery and bootstrap**

Создать локальный venv через `venv.EnvBuilder(with_pip=True)`, проверить пакет командой `python -c "import parser_2gis"`, при необходимости выполнить `python -m pip install --disable-pip-version-check -r <requirements>` и вернуть команду `python -c "from parser_2gis import main; main()"`.

- [ ] **Step 3: Run runtime tests**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_parser2gis_runtime -v`

Expected: PASS для готового, нового и пользовательского runtime.

### Task 3: Parser Integration

**Files:**
- Modify: `backend/parser.py`
- Test: `backend/tests/test_parser_start_page.py`

**Interfaces:**
- Consumes: `ensure_parser2gis_command(on_status)` из Task 2.
- Produces: список нормализованных лидов из реального JSON upstream-парсера.

- [ ] **Step 1: Replace legacy runner construction**

Удалить константы `PARSER2GIS_DIR`, `PARSER2GIC_DIR`, `PARSE_RUNNER`, `CITIES_FILE` и проверки внешних файлов. Построить `cmd` из `ensure_parser2gis_command(on_status)` и официальных CLI-флагов.

- [ ] **Step 2: Preserve robust process handling**

Запускать CLI из `ROOT_DIR`, оставить UTF-8-окружение, таймаут, хвост stdout при ошибке и проверку непустого выходного JSON. Читать headed-настройку из `PARSER2GIS_HEADLESS` с fallback на `LEADHUNT_HEADLESS`.

- [ ] **Step 3: Run focused parser tests**

Run: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_parser_start_page backend.tests.test_parser2gis_runtime -v`

Expected: PASS.

### Task 4: Documentation and End-to-End Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: runtime configuration and verified commands from Tasks 2–3.
- Produces: setup and troubleshooting instructions matching actual behavior.

- [ ] **Step 1: Update environment documentation**

Добавить `PARSER2GIS_HEADLESS=no`, `PARSER2GIS_RUNTIME_DIR=` и `PARSER2GIS_PYTHON=`; удалить утверждения о необходимости `parser2gic` для 2ГИС.

- [ ] **Step 2: Run a live one-record parse**

Run: `backend\.venv\Scripts\python.exe -c "from backend.parser import collect_2gis; print(collect_2gis('Москва', 'аптеки', 1))"`

Expected: список минимум с одной карточкой, непустыми `name`, `address` и хотя бы одним элементом `contacts`.

- [ ] **Step 3: Run the full verification suite**

Run: `backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v`

Expected: all backend tests PASS.

Run: `pnpm run build`

Expected: TypeScript и Vite завершаются с exit code 0.

- [ ] **Step 4: Commit and push**

```text
git add .env.example README.md backend/parser.py backend/parser2gis_runtime.py backend/parser2gis-requirements.txt backend/tests/test_parser_start_page.py backend/tests/test_parser2gis_runtime.py docs/superpowers/specs/2026-07-22-parser2gis-runtime-design.md docs/superpowers/plans/2026-07-22-parser2gis-runtime.md
git commit -m "fix: make 2gis parser self-contained"
git push origin main
```
