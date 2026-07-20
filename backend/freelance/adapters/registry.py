from __future__ import annotations

from .browser import ProfiAdapter, WorkzillaAdapter, YoudoAdapter
from .public import FlAdapter, FreelanceRuAdapter, FreelancehuntAdapter, KworkAdapter


def adapter_registry() -> dict[str, type]:
    return {
        "kwork": KworkAdapter,
        "fl": FlAdapter,
        "freelance_ru": FreelanceRuAdapter,
        "workzilla": WorkzillaAdapter,
        "freelancehunt": FreelancehuntAdapter,
        "profi": ProfiAdapter,
        "youdo": YoudoAdapter,
    }
