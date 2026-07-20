# Semix CRM backend

Бэкенд питает раздел «Волк с Уолл-стрит»: сохраняет бизнесы в SQLite,
запускает парсеры 2GIS и Яндекс Карт, хранит настройки, статусы клиентов и
историю запусков. База по умолчанию находится в
`backend/data/semixcrm.sqlite3`.

```powershell
cd C:\Users\Admin\Desktop\SemixCRM
py -3 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
py -3 -m playwright install chromium
npm run dev
```

`npm run dev` запускает frontend на `http://127.0.0.1:5173` и backend на
`http://127.0.0.1:8000` в одном процессе. Если API уже запущен, новый процесс
использует его и не создаёт второй сервер.

Парсер использует текущую установку `py -3` (или `LEADHUNT_PYTHON`), потому
что прежний LeadHunt virtualenv больше невалиден. При переносе проекта можно
переопределить `LEADHUNT_ROOT`, `PARSER2GIC_ROOT` и `LEADHUNT_HEADLESS`.

Основные endpoints:

- `GET/PUT /api/parser/settings` — город, ниши, источники и лимит;
- `POST /api/clients/parse` — фоновый запуск 2GIS/Яндекс Карт;
- `GET /api/clients/jobs/{job_id}` — прогресс запуска;
- `GET /api/parser/runs` — история запусков;
- `GET /api/clients` — клиенты и агрегированная статистика;
- `PUT /api/clients/{client_id}/status` — изменение этапа клиента.

## Фриланс и локальный снайпер

Раздел «Фриланс» хранит только полученные или добавленные вами заказы в SQLite.
Демонстрационные карточки не создаются. Снайпер работает локально, пока запущен
backend Semix CRM, и проверяет включённые источники с заданным интервалом.

Установка зависимостей и браузера:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m playwright install chromium
```

Скопируйте `.env.example` в `.env` и заполните только локальные значения:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_ID=800395558
FREELANCE_BROWSER_PROFILE=backend/data/freelance_browser
FREELANCE_BROWSER_CHANNEL=chrome
FREELANCE_CHROME_PATH=
FREELANCE_POLL_INTERVAL_SECONDS=60
```

Токен Telegram читается только из `.env` и используется только для указанного
`TELEGRAM_ALLOWED_CHAT_ID`. Токен, ранее отправленный в чат, необходимо сначала
отозвать и выпустить заново через BotFather. Не добавляйте секреты, cookies или
SQLite-файлы в Git.

Источники Kwork, FL.ru и Freelance.ru читаются из публичных лент. Workzilla,
Profi.ru и YouDo используют постоянный локальный Chromium-профиль. CRM сначала
ищет установленный Google Chrome. При необходимости путь можно указать через
`FREELANCE_CHROME_PATH` или установить Chromium командой
`backend\.venv\Scripts\python.exe -m playwright install chromium`.
В интерфейсе нажмите «Настроить» → «Открыть вход»,
войдите вручную и закройте окно. Пароли не передаются CRM, CAPTCHA и ограничения
доступа не обходятся. URL ленты можно переопределить переменными
`FREELANCE_WORKZILLA_URL`, `FREELANCE_PROFI_URL` и `FREELANCE_YOUDO_URL`.

Основные API раздела:

- `GET/POST /api/freelance/orders` — активные заказы и ручное добавление;
- `GET /api/freelance/orders?archived=true` — отдельный список скрытых заказов;
- `PUT/DELETE /api/freelance/orders/{id}` — статус, заметка и скрытие;
- `GET/PUT /api/freelance/settings` — источники, ключевые слова, бюджет и режимы;
- `POST /api/freelance/sniper/start|stop|check` — управление снайпером;
- `GET /api/freelance/sources` — последнее состояние каждого источника;
- `POST /api/freelance/sources/{source}/auth` — открыть локальное окно входа;
- `GET /api/freelance/runs` и `/api/freelance/runs/{id}` — история запусков и
  точный набор карточек, увиденных в выбранный момент.

Каждый источник изолирован: ошибка или истёкшая сессия отображается рядом с ним
и не скрывает уже сохранённые заказы. Дубликаты определяются по `source` и
внешнему ID, а уведомление Telegram записывается не более одного раза для
разрешённого chat ID.
