from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_environment(path: Path | None = None) -> bool:
    """Load local defaults while preserving values explicitly set by the shell."""

    return load_dotenv(dotenv_path=path or PROJECT_ROOT / ".env", override=False)
