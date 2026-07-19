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
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

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
