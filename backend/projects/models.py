from __future__ import annotations

from dataclasses import dataclass, field


PROJECT_STATUSES = ("В работе", "Готов", "Пауза")
PROJECT_CATEGORIES = ("Веб-приложение", "Веб-сайт", "Бот", "Скрипт", "Мобильное", "Другое")

# Состояния запущенного процесса, которые видит интерфейс.
RUNTIME_STOPPED = "stopped"
RUNTIME_STARTING = "starting"
RUNTIME_RUNNING = "running"
RUNTIME_EXITED = "exited"
RUNTIME_FAILED = "failed"


@dataclass(frozen=True)
class Project:
    name: str
    description: str = ""
    path: str = ""
    command: str = ""
    url: str = ""
    port: int | None = None
    tags: tuple[str, ...] = ()
    category: str = "Веб-приложение"
    status: str = "В работе"
    version: str = ""
    repo_url: str = ""
    progress: int = 0

    def validated(self) -> "Project":
        if not self.name.strip():
            raise ValueError("Укажите название проекта")
        if self.status not in PROJECT_STATUSES:
            raise ValueError("Неизвестный статус проекта")
        if self.port is not None and not (1 <= self.port <= 65535):
            raise ValueError("Порт должен быть в диапазоне 1–65535")
        return self


@dataclass
class DetectedProject:
    """Результат разбора папки проекта перед добавлением."""

    name: str = ""
    description: str = ""
    command: str = ""
    port: int | None = None
    version: str = ""
    category: str = "Веб-приложение"
    tags: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    exists: bool = False
    kind: str = "unknown"

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "command": self.command,
            "port": self.port,
            "version": self.version,
            "category": self.category,
            "tags": self.tags,
            "scripts": self.scripts,
            "exists": self.exists,
            "kind": self.kind,
        }
