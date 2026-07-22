from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


AUTH_URLS = {
    "profi": "https://profi.ru/backoffice/a.php",
    "youdo": "https://youdo.com/tasks",
}

_login_processes: dict[str, subprocess.Popen[Any]] = {}
_login_lock = threading.Lock()


def browser_profile_path(source: str | None = None) -> Path:
    value = os.getenv("FREELANCE_BROWSER_PROFILE", "backend/data/freelance_browser")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if source:
        safe_source = "".join(character for character in source.strip().lower() if character.isalnum() or character in {"-", "_"})
        if safe_source:
            path /= safe_source
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def browser_channel() -> str | None:
    value = os.getenv("FREELANCE_BROWSER_CHANNEL", "chrome").strip()
    return value or None


def find_chrome_executable() -> Path | None:
    """Return a locally installed Chromium browser without requiring a Playwright download."""

    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    candidates = [
        os.getenv("FREELANCE_CHROME_PATH", "").strip(),
        str(Path(local_app_data) / "Google/Chrome/Application/chrome.exe") if local_app_data else "",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("chrome") or "",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    return None


def _missing_browser_error(error: Exception, source: str | None = None) -> RuntimeError:
    message = str(error)
    compact_message = " ".join(message.split())
    source_labels = {"profi": "Profi.ru", "youdo": "YouDo"}
    source_label = source_labels.get(source or "", "этой площадки")
    if "Target page, context or browser has been closed" in message or "exitCode=21" in message:
        return RuntimeError(f"Профиль {source_label} занят другим окном. Закройте окно входа {source_label} и повторите проверку.")
    if "Executable doesn't exist" in message or "browserType.launch" in message or "Chromium distribution" in message:
        return RuntimeError(
            "Браузер для парсера не найден. Установите Google Chrome или выполните "
            "backend\\.venv\\Scripts\\python.exe -m playwright install chromium"
        )
    return RuntimeError(f"Не удалось запустить браузер парсера: {compact_message[:280]}")


class PersistentBrowserSession:
    """Own a Playwright persistent context in the thread that created it."""

    def __init__(self, *, source: str | None = None, headless: bool = True) -> None:
        self._source = source
        self._playwright = sync_playwright().start()
        options: dict[str, Any] = {
            "user_data_dir": str(browser_profile_path(source)),
            "headless": headless,
            "locale": "ru-RU",
            "viewport": {"width": 1440, "height": 1000},
        }
        if not headless:
            options["args"] = ["--start-minimized"]
        executable = find_chrome_executable()
        if executable:
            options["executable_path"] = executable.as_posix()
        else:
            channel = browser_channel()
            if channel:
                options["channel"] = channel
        try:
            self._context = self._playwright.chromium.launch_persistent_context(**options)
        except Exception as first_error:
            if "channel" not in options:
                self._playwright.stop()
                raise _missing_browser_error(first_error, source) from first_error
            options.pop("channel", None)
            try:
                self._context = self._playwright.chromium.launch_persistent_context(**options)
            except Exception as fallback_error:
                self._playwright.stop()
                raise _missing_browser_error(fallback_error, source) from fallback_error
        self._closed = False

    def new_page(self):
        if self._context.pages:
            return self._context.pages[0]
        return self._context.new_page()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._context.close()
        finally:
            self._playwright.stop()


def persistent_browser_factory(source: str | None = None, headless: bool = True) -> PersistentBrowserSession:
    return PersistentBrowserSession(source=source, headless=headless)


def open_login_window(source: str) -> dict[str, Any]:
    """Open a visible local login window in a helper process."""

    if source not in AUTH_URLS:
        raise ValueError("Для этого источника отдельный вход не требуется")
    with _login_lock:
        current = _login_processes.get(source)
        if current is not None and current.poll() is None:
            return {"source": source, "status": "already_open", "pid": current.pid}
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            [sys.executable, "-m", "backend.freelance.browser_login", source],
            cwd=str(Path(__file__).resolve().parents[2]),
            creationflags=flags,
            close_fds=True,
        )
        _login_processes[source] = process
        return {"source": source, "status": "opened", "pid": process.pid}
