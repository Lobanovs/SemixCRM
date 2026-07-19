import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'

const root = resolve(import.meta.dirname, '..')
const apiUrl = 'http://127.0.0.1:8000/api/health'
const pythonVenv = resolve(root, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const pythonCommand = existsSync(pythonVenv) ? pythonVenv : (process.platform === 'win32' ? 'py' : 'python3')
const pythonPrefix = existsSync(pythonVenv) ? [] : (process.platform === 'win32' ? ['-3'] : [])
const children = []
let shuttingDown = false

async function apiIsReady() {
  try {
    const response = await fetch(apiUrl)
    return response.ok
  } catch {
    return false
  }
}

async function frontendIsReady() {
  try {
    const response = await fetch('http://127.0.0.1:5173')
    return response.ok
  } catch {
    return false
  }
}

async function waitForApi(timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await apiIsReady()) return true
    await delay(250)
  }
  return false
}

function stopChild(child) {
  if (!child || child.killed) return
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore', windowsHide: true })
  } else {
    child.kill('SIGTERM')
  }
}

function shutdown(code = 0) {
  if (shuttingDown) return
  shuttingDown = true
  for (const child of children) stopChild(child)
  setTimeout(() => process.exit(code), 100)
}

process.on('SIGINT', () => shutdown(0))
process.on('SIGTERM', () => shutdown(0))

if (!(await apiIsReady())) {
  const api = spawn(pythonCommand, [
    ...pythonPrefix,
    '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000',
  ], {
    cwd: root,
    env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    stdio: 'inherit',
    windowsHide: true,
  })
  children.push(api)
  api.on('error', (error) => console.error(`[Semix CRM] Не удалось запустить backend: ${error.message}`))
  if (!(await waitForApi())) {
    console.warn('[Semix CRM] Backend не ответил за 15 секунд. Проверьте backend/.venv и порт 8000.')
  }
} else {
  console.log('[Semix CRM] Backend уже запущен на http://127.0.0.1:8000')
}

if (await frontendIsReady()) {
  console.log('[Semix CRM] Frontend already running on http://127.0.0.1:5173')
} else {
  const vite = spawn(process.execPath, [
    resolve(root, 'node_modules', 'vite', 'bin', 'vite.js'),
    '--host', '127.0.0.1', '--port', '5173', '--strictPort',
  ], {
    cwd: root,
    env: process.env,
    stdio: 'inherit',
    windowsHide: true,
  })
  children.push(vite)
  vite.on('error', (error) => {
    console.error(`[Semix CRM] Failed to start frontend: ${error.message}`)
    shutdown(1)
  })
  vite.on('exit', (code) => {
    if (!shuttingDown) shutdown(code ?? 0)
  })
}
