from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import RUNTIME_EXITED, RUNTIME_FAILED, RUNTIME_RUNNING, RUNTIME_STOPPED


IS_WINDOWS = sys.platform == "win32"
LOG_LIMIT = 400

# Vite и остальные дев-серверы раскрашивают вывод. Без очистки эти последовательности
# попадали и в лог на экране, и внутрь адреса: http://127.0.0.1:\x1b[1m5205\x1b[22m/
ANSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

# Сообщения вида "Local: http://localhost:5173/" — так дев-серверы печатают свой адрес.
URL_PATTERN = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::(\d{2,5}))?[^\s\"'<>]*")

# Частые причины падения: сырой стек Node ничего не объясняет.
FAILURE_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"port\s+(\d{2,5})\s+is already in use", re.IGNORECASE),
     "Порт {0} уже занят другим процессом. Освободите его или смените порт в настройках проекта."),
    (re.compile(r"EADDRINUSE.*?:(\d{2,5})", re.IGNORECASE),
     "Порт {0} уже занят другим процессом. Освободите его или смените порт в настройках проекта."),
    (re.compile(r"(?:cannot find module|module not found|ERR_MODULE_NOT_FOUND)", re.IGNORECASE),
     "Не найдены зависимости. Выполните npm install в папке проекта."),
    (re.compile(r"(?:'\w+' is not recognized|command not found|ENOENT)", re.IGNORECASE),
     "Команда запуска не найдена. Проверьте, что она выполняется в терминале из папки проекта."),
    (re.compile(r"missing script", re.IGNORECASE),
     "В package.json нет такого скрипта. Проверьте команду запуска."),
)


def strip_ansi(value: str) -> str:
    return ANSI_PATTERN.sub("", value)


def explain_failure(lines: list[str]) -> str:
    """Человеческое объяснение падения по последним строкам лога."""

    tail = "\n".join(lines[-40:])
    for pattern, template in FAILURE_HINTS:
        match = pattern.search(tail)
        if match is not None:
            return template.format(*match.groups()) if match.groups() else template
    meaningful = [line.strip() for line in lines if line.strip()]
    return meaningful[-1][:200] if meaningful else ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectProcess:
    """Один запущенный проект: процесс, его логи и обнаруженный адрес."""

    def __init__(self, project_id: int, name: str, command: str, cwd: str, popen: subprocess.Popen[str]) -> None:
        self.project_id = project_id
        self.name = name
        self.command = command
        self.cwd = cwd
        self.popen = popen
        self.started_at = _now()
        self.logs: deque[str] = deque(maxlen=LOG_LIMIT)
        self.url = ""
        self.port: int | None = None
        self.lock = threading.Lock()
        self.reader = threading.Thread(target=self._read_output, daemon=True, name=f"semix-project-{project_id}")
        self.reader.start()

    def _read_output(self) -> None:
        stream = self.popen.stdout
        if stream is None:
            return
        try:
            for line in stream:
                # Чистим цвета сразу: иначе они уедут и в лог на экране, и в адрес.
                text = strip_ansi(line.rstrip("\r\n"))
                with self.lock:
                    self.logs.append(text)
                    if not self.url:
                        self._sniff_url(text)
        except (ValueError, OSError):
            # Поток закрыт при остановке процесса — это штатное завершение чтения.
            pass
        finally:
            try:
                stream.close()
            except (ValueError, OSError):
                pass

    def _sniff_url(self, line: str) -> None:
        match = URL_PATTERN.search(line)
        if match is None:
            return
        self.url = match.group(0).rstrip(".,;)")
        if match.group(1):
            self.port = int(match.group(1))

    def is_alive(self) -> bool:
        return self.popen.poll() is None

    def snapshot(self, fallback_url: str = "", fallback_port: int | None = None) -> dict[str, Any]:
        code = self.popen.poll()
        if code is None:
            status = RUNTIME_RUNNING
        elif code == 0:
            status = RUNTIME_EXITED
        else:
            status = RUNTIME_FAILED
        with self.lock:
            url = self.url
            port = self.port
            lines = list(self.logs)
        resolved_port = port or fallback_port
        if not url and resolved_port:
            url = f"http://localhost:{resolved_port}"
        return {
            "project_id": self.project_id,
            "status": status,
            "pid": self.popen.pid,
            "started_at": self.started_at,
            "command": self.command,
            "cwd": self.cwd,
            "url": url or fallback_url,
            "port": resolved_port,
            "exit_code": code,
            "last_line": lines[-1] if lines else "",
            # Для упавшего процесса показываем причину, а не последнюю строку стека.
            "reason": explain_failure(lines) if status == RUNTIME_FAILED else "",
        }

    def read_logs(self, limit: int = LOG_LIMIT) -> list[str]:
        with self.lock:
            return list(self.logs)[-limit:]


def _terminate(popen: subprocess.Popen[str]) -> None:
    """Убивает процесс вместе с потомками: дев-сервер обычно порождает дерево."""

    if popen.poll() is not None:
        return
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(popen.pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            popen.kill()
    else:
        try:
            os.killpg(os.getpgid(popen.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            popen.terminate()
    try:
        popen.wait(timeout=10)
    except subprocess.TimeoutExpired:
        popen.kill()


class ProjectRunner:
    """Держит запущенные проекты в памяти процесса backend."""

    def __init__(self) -> None:
        self._processes: dict[int, ProjectProcess] = {}
        self._lock = threading.Lock()

    def _spawn(self, command: str, cwd: str) -> subprocess.Popen[str]:
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
        return subprocess.Popen(
            command,
            cwd=cwd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creation_flags,
            start_new_session=not IS_WINDOWS,
        )

    def start(self, project: dict[str, Any]) -> dict[str, Any]:
        project_id = int(project["id"])
        command = str(project.get("command") or "").strip()
        raw_path = str(project.get("path") or "").strip()
        if not command:
            raise ValueError("У проекта не задана команда запуска")
        if not raw_path:
            raise ValueError("У проекта не задана папка")
        folder = Path(raw_path).expanduser()
        if not folder.is_dir():
            raise ValueError(f"Папка проекта не найдена: {folder}")

        with self._lock:
            current = self._processes.get(project_id)
            if current is not None and current.is_alive():
                raise ValueError("Проект уже запущен")
            if current is not None:
                self._processes.pop(project_id, None)
            try:
                popen = self._spawn(command, str(folder))
            except OSError as error:
                raise ValueError(f"Не удалось запустить команду: {error}") from error
            process = ProjectProcess(project_id, str(project.get("name") or ""), command, str(folder), popen)
            self._processes[project_id] = process
        return process.snapshot(str(project.get("url") or ""), project.get("port"))

    def stop(self, project_id: int) -> dict[str, Any]:
        with self._lock:
            process = self._processes.pop(int(project_id), None)
        if process is None:
            return {"project_id": int(project_id), "status": RUNTIME_STOPPED, "url": "", "port": None}
        _terminate(process.popen)
        return {**process.snapshot(), "status": RUNTIME_STOPPED}

    def status(self, project: dict[str, Any]) -> dict[str, Any]:
        project_id = int(project["id"])
        with self._lock:
            process = self._processes.get(project_id)
        if process is None:
            return {
                "project_id": project_id,
                "status": RUNTIME_STOPPED,
                "pid": None,
                "started_at": "",
                "url": str(project.get("url") or ""),
                "port": project.get("port"),
                "exit_code": None,
                "last_line": "",
                "reason": "",
            }
        return process.snapshot(str(project.get("url") or ""), project.get("port"))

    def statuses(self, projects: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {str(project["id"]): self.status(project) for project in projects}

    def logs(self, project_id: int, limit: int = LOG_LIMIT) -> list[str]:
        with self._lock:
            process = self._processes.get(int(project_id))
        return process.read_logs(limit) if process is not None else []

    def is_running(self, project_id: int) -> bool:
        with self._lock:
            process = self._processes.get(int(project_id))
        return process is not None and process.is_alive()

    def stop_all(self) -> int:
        with self._lock:
            processes = list(self._processes.values())
            self._processes.clear()
        for process in processes:
            _terminate(process.popen)
        return len(processes)
