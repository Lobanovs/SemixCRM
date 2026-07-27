from __future__ import annotations

from typing import Any

from .habr import HabrAdapter
from .hh import HhAdapter
from .remote import RemoteOkAdapter, RemotiveAdapter, WeWorkRemotelyAdapter
from .telegram import TelegramAdapter


# Чтобы добавить площадку: наследуйте HttpJobAdapter, реализуйте request_urls и parse,
# затем добавьте класс сюда и в JOB_SOURCES в models.py.
def adapter_registry() -> dict[str, type]:
    return {
        "hh": HhAdapter,
        "habr": HabrAdapter,
        "telegram": TelegramAdapter,
        "remoteok": RemoteOkAdapter,
        "remotive": RemotiveAdapter,
        "weworkremotely": WeWorkRemotelyAdapter,
    }


def build_job_adapters() -> dict[str, Any]:
    return {source: adapter_type() for source, adapter_type in adapter_registry().items()}
