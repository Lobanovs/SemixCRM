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

При первом запуске источника 2GIS backend создаёт отдельное окружение
`backend/data/parser2gis-runtime` и устанавливает туда `parser-2gis==1.2.1`.
Так Pydantic 1.x парсера не конфликтует с Pydantic 2.x основного API. Внешний
каталог `parser2gic` больше не нужен. Для сбора требуется Google Chrome;
headless-режим по умолчанию отключён, поскольку 2GIS может показать CAPTCHA.

Каталог окружения можно изменить через `PARSER2GIS_RUNTIME_DIR`. Переменная
`PARSER2GIS_PYTHON` указывает готовый Python с установленным upstream-пакетом,
а `PARSER2GIS_HEADLESS` управляет режимом Chrome. `LEADHUNT_ROOT` и
`LEADHUNT_PYTHON` относятся только к источнику Яндекс Карт.

Основные endpoints:

- `GET/PUT /api/parser/settings` — город, ниши, источники, стартовая страница и объём;
- `POST /api/clients/parse` — фоновый запуск 2GIS/Яндекс Карт;
- `GET /api/clients/jobs/{job_id}` — прогресс запуска;
- `GET /api/parser/runs` — история запусков;
- `GET /api/clients` — клиенты и агрегированная статистика;
- `PUT /api/clients/{client_id}/status` — изменение этапа клиента.

Для 2GIS значение `limit: 0` включает полный проход от `start_page` до конца
выдачи. Положительный лимит не ограничен прежними 50 компаниями. Итоговый JSON
в полном режиме не обрезается, а пустой успешный ответ 2GIS автоматически
повторяется один раз. Яндекс Карты по-прежнему собирают не более 50 компаний
на нишу.

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
FREELANCE_YOUDO_MAX_TASKS=500
PARSER2GIS_RUNTIME_DIR=backend/data/parser2gis-runtime
PARSER2GIS_PYTHON=
PARSER2GIS_HEADLESS=no
```

Токен Telegram читается только из `.env` и используется только для указанного
`TELEGRAM_ALLOWED_CHAT_ID`. Токен, ранее отправленный в чат, необходимо сначала
отозвать и выпустить заново через BotFather. Не добавляйте секреты, cookies или
SQLite-файлы в Git.

Источники Kwork, FL.ru и Freelance.ru читаются из публичных лент. Profi.ru и
YouDo используют отдельные постоянные локальные Chromium-профили. CRM сначала
ищет установленный Google Chrome. При необходимости путь можно указать через
`FREELANCE_CHROME_PATH` или установить Chromium командой
`backend\.venv\Scripts\python.exe -m playwright install chromium`.
В интерфейсе нажмите «Настроить» → «Войти»,
войдите вручную и закройте окно. Пароли не передаются CRM, CAPTCHA и ограничения
доступа не обходятся. URL страниц можно переопределить переменными
`FREELANCE_PROFI_URL` и `FREELANCE_YOUDO_URL`. YouDo при блокировке headless-запроса
повторяется в видимом свёрнутом Chrome; лимит карточек задаёт
`FREELANCE_YOUDO_MAX_TASKS` (по умолчанию 500).

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

### Browser profile isolation

Each browser-based freelance source uses its own persistent profile under
`backend/data/freelance_browser`: `profi` and `youdo`. After upgrading, use
Settings -> Sign in once for each source, sign in, and close the login window
before pressing Check now. Chrome cannot run a second process against the same
persistent profile while the login window is open.
