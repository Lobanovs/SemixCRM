# Bulk Vacancy Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить безопасную кнопку «Все в архив», которая одним защищённым запросом архивирует все активные вакансии и обновляет интерфейс.

**Architecture:** Хранилище выполняет массовое обновление одной SQL-командой и возвращает число затронутых строк. FastAPI публикует отдельный защищённый маршрут до параметризованного маршрута вакансии, а React-страница подтверждает действие, блокирует повторный запуск и перезагружает список.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, React 19, TypeScript, Vitest, Testing Library.

## Global Constraints

- Архивирование не удаляет вакансии и затрагивает только записи с `archived = 0`.
- Действие относится ко всей активной базе, а не только к текущим фильтрам.
- Маршрут требует заголовок `X-Requested-With: SemixCRM` через `guard_powerful_action`.
- Повторный вызов идемпотентен и возвращает `archived_count: 0`.

---

### Task 1: Backend массового архивирования

**Files:**
- Modify: `backend/tests/test_jobs_api.py`
- Modify: `backend/jobs/storage.py`
- Modify: `backend/main.py`

**Interfaces:**
- Produces: `jobs_storage.archive_all_jobs() -> int`
- Produces: `POST /api/jobs/archive-all -> {"ok": true, "archived_count": int}`

- [ ] **Step 1: Write the failing API test**

Добавить в `JobsApiTests` тест, который создаёт две активные вакансии и одну уже архивную, вызывает маршрут дважды и проверяет активный список, архив и счётчики:

```python
def test_archive_all_moves_every_active_job_and_is_idempotent(self) -> None:
    first_id = self.client.post("/api/jobs", json={"role": "Frontend"}).json()["id"]
    old_id = self.client.post("/api/jobs", json={"role": "Уже в архиве"}).json()["id"]
    self.client.post("/api/jobs", json={"role": "Backend"})
    self.client.put(f"/api/jobs/{old_id}", json={"archived": True})

    response = self.client.post("/api/jobs/archive-all")

    self.assertEqual(200, response.status_code)
    self.assertEqual({"ok": True, "archived_count": 2}, response.json())
    self.assertEqual([], self.client.get("/api/jobs").json()["jobs"])
    self.assertEqual(3, len(self.client.get("/api/jobs?archived=true").json()["jobs"]))
    self.assertEqual(0, self.client.post("/api/jobs/archive-all").json()["archived_count"])
    self.assertIn(first_id, [item["id"] for item in self.client.get("/api/jobs?archived=true").json()["jobs"]])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\\.venv\\Scripts\\python.exe -m unittest backend.tests.test_jobs_api.JobsApiTests.test_archive_all_moves_every_active_job_and_is_idempotent -v`

Expected: FAIL because `/api/jobs/archive-all` does not exist.

- [ ] **Step 3: Implement storage and route**

Добавить в `backend/jobs/storage.py`:

```python
def archive_all_jobs() -> int:
    with _connect() as connection:
        cursor = connection.execute(
            "UPDATE jobs SET archived = 1, updated_at = ? WHERE archived = 0",
            (_now(),),
        )
    return max(0, cursor.rowcount)
```

Добавить в `backend/main.py` до `/api/jobs/{job_id}`:

```python
@app.post("/api/jobs/archive-all", dependencies=[Depends(guard_powerful_action)])
def archive_all_job_items() -> dict[str, Any]:
    return {"ok": True, "archived_count": jobs_storage.archive_all_jobs()}
```

- [ ] **Step 4: Run backend tests**

Run: `backend\\.venv\\Scripts\\python.exe -m unittest backend.tests.test_jobs_api -v`

Expected: all jobs API tests PASS.

---

### Task 2: Кнопка и обратная связь на фронтенде

**Files:**
- Modify: `src/pages/JobsPage.test.tsx`
- Modify: `src/pages/JobsPage.tsx`
- Modify: `src/styles.css`

**Interfaces:**
- Consumes: `POST /api/jobs/archive-all`
- Produces: кнопка `Все в архив` только в активном списке; сообщение `Перенесено в архив: N`.

- [ ] **Step 1: Write failing interaction tests**

Расширить fetch-мок обработкой `POST /api/jobs/archive-all` до общего обработчика создания вакансии, а затем добавить два теста: подтверждённое действие отправляет POST с защитным заголовком и отмена не отправляет POST.

```tsx
if (method === 'POST' && url.includes('/api/jobs/archive-all')) {
  return jsonResponse({ ok: true, archived_count: overrides.jobs?.length ?? 1 })
}
```

```tsx
it('архивирует все активные вакансии после подтверждения', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('confirm', vi.fn(() => true))
  vi.stubGlobal('fetch', createFetchMock())
  render(<JobsPage />)

  await user.click(await screen.findByRole('button', { name: 'Все в архив' }))

  await waitFor(() => {
    const call = vi.mocked(fetch).mock.calls.find(([url, init]) =>
      init?.method === 'POST' && String(url).endsWith('/api/jobs/archive-all'))
    expect(call).toBeDefined()
    expect((call?.[1]?.headers as Record<string, string>)['X-Requested-With']).toBe('SemixCRM')
  })
  expect(await screen.findByText('Перенесено в архив: 1')).toBeVisible()
})

it('не архивирует вакансии после отмены подтверждения', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('confirm', vi.fn(() => false))
  vi.stubGlobal('fetch', createFetchMock())
  render(<JobsPage />)

  await user.click(await screen.findByRole('button', { name: 'Все в архив' }))

  expect(vi.mocked(fetch).mock.calls.some(([url, init]) =>
    init?.method === 'POST' && String(url).endsWith('/api/jobs/archive-all'))).toBe(false)
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test:frontend -- src/pages/JobsPage.test.tsx`

Expected: FAIL because the button is missing.

- [ ] **Step 3: Implement the interaction**

Добавить состояние `archivingAll` и `notice`, обработчик с подтверждением и запросом через `apiRequest`, затем отрисовать кнопку только при `!archived`:

```tsx
const archiveAllJobs = async () => {
  const count = stats?.total ?? jobs.length
  if (!count || !window.confirm(`Перенести все активные вакансии (${count}) в архив?`)) return
  setArchivingAll(true)
  setError('')
  try {
    const result = await apiRequest<{ archived_count: number }>('/api/jobs/archive-all', {
      method: 'POST', fallback: 'Не удалось архивировать вакансии',
    })
    setNotice(`Перенесено в архив: ${result.archived_count}`)
    await load()
  } catch (archiveError) {
    setError(archiveError instanceof Error ? archiveError.message : 'Не удалось архивировать вакансии')
  } finally {
    setArchivingAll(false)
  }
}
```

Кнопка получает иконку `Archive`, `aria-live="polite"` используется для сообщения, а CSS задаёт различимый опасный outline-стиль, видимый focus и состояние disabled без изменения сетки тулбара.

- [ ] **Step 4: Run frontend tests**

Run: `npm run test:frontend -- src/pages/JobsPage.test.tsx`

Expected: all JobsPage tests PASS.

---

### Task 3: Полная проверка и публикация

**Files:**
- Verify: `backend/tests/test_jobs_api.py`
- Verify: `src/pages/JobsPage.test.tsx`

**Interfaces:**
- Consumes: завершённые backend и frontend изменения.
- Produces: проверенный и опубликованный коммит.

- [ ] **Step 1: Run the complete automated verification**

Run: `backend\\.venv\\Scripts\\python.exe -m unittest discover -s backend/tests -v`

Run: `npm run check`

Run: `npm audit --audit-level=moderate`

Expected: backend and frontend tests PASS, production build succeeds, audit reports 0 vulnerabilities.

- [ ] **Step 2: Verify in the browser**

Открыть `http://127.0.0.1:5173/#jobs`, отменить подтверждение и убедиться, что список не изменился. Затем подтвердить действие на тестовых данных, проверить пустой активный список, увеличившийся счётчик архива и возможность вернуть вакансию.

- [ ] **Step 3: Inspect and commit**

Run: `git diff --check`

Run: `git status --short`

Commit: `feat: archive all vacancies`

- [ ] **Step 4: Push and verify CI**

Run: `git push origin main`

Run: `gh run watch --exit-status`

Expected: GitHub Actions completes successfully for the pushed commit.
