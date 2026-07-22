from __future__ import annotations

from typing import Any, Callable

from .browser import ProfiAdapter, YoudoAdapter
from .public import FlAdapter, FreelanceRuAdapter, KworkAdapter


def adapter_registry() -> dict[str, type]:
    return {
        "kwork": KworkAdapter,
        "fl": FlAdapter,
        "freelance_ru": FreelanceRuAdapter,
        "profi": ProfiAdapter,
        "youdo": YoudoAdapter,
    }


def build_adapters(browser_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Create adapters and inject the persistent session into browser sources."""

    adapters: dict[str, Any] = {}
    for source, adapter_type in adapter_registry().items():
        if getattr(adapter_type, "requires_browser", False):
            adapters[source] = adapter_type(browser_factory=browser_factory)
        else:
            adapters[source] = adapter_type()
    return adapters
