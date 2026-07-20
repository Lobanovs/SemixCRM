from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


AUTH_URLS = {
    "workzilla": "https://client.work-zilla.com/account/login?isFreelancer=true&ReturnUrl=%2Ffreelancer",
    "profi": "https://profi.ru/backoffice/a.php",
    "youdo": "https://youdo.com/tasks",
}

_login_processes: dict[str, subprocess.Popen[Any]] = {}
_login_lock = threading.Lock()


def browser_profile_path() -> Path:
    value = os.getenv("FREELANCE_BROWSER_PROFILE", "backend/data/freelance_browser")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def browser_channel() -> str | None:
    value = os.getenv("FREELANCE_BROWSER_CHANNEL", "chrome").strip()
    return value or None


class PersistentBrowserSession:
    """Own a Playwright persistent context in the thread that created it."""

    def __init__(self, *, headless: bool = True) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        options: dict[str, Any] = {
            "user_data_dir": str(browser_profile_path()),
            "headless": headless,
            "locale": "ru-RU",
            "viewport": {"width": 1440, "height": 1000},
        }
        channel = browser_channel()
        if channel:
            options["channel"] = channel
        try:
            self._context = self._playwright.chromium.launch_persistent_context(**options)
        except Exception:
            if "channel" not in options:
                self._playwright.stop()
                raise
            options.pop("channel", None)
            try:
                self._context = self._playwright.chromium.launch_persistent_context(**options)
            except Exception:
                self._playwright.stop()
                raise
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


def persistent_browser_factory() -> PersistentBrowserSession:
    return PersistentBrowserSession(headless=True)


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
