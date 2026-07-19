# Semix CRM backend

The first backend slice powers the «Волк с Уолл-стрит» client parser. It reuses
the LeadHunt `parser-2gis` runner and stores normalized businesses in SQLite at
`backend/data/semixcrm.sqlite3`.

```powershell
cd C:\Users\Admin\Desktop\SemixCRM
py -3 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The parser subprocess uses the current `py -3` installation (or
`LEADHUNT_PYTHON`) because the original LeadHunt Python 3.13 virtualenv is no
longer valid. Override `LEADHUNT_ROOT`, `PARSER2GIC_ROOT`, or `LEADHUNT_HEADLESS`
when moving the workspace.
