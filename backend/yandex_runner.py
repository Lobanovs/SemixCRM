from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path


def main() -> None:
    arguments = argparse.ArgumentParser(description="LeadHunt Yandex Maps bridge")
    arguments.add_argument("--city", required=True)
    arguments.add_argument("--niche", required=True)
    arguments.add_argument("--limit", required=True, type=int)
    arguments.add_argument("--output", required=True)
    args = arguments.parse_args()

    leadhunt_root = Path(os.getenv("LEADHUNT_ROOT", r"C:\Users\Admin\Desktop\LeadHunt"))
    if not leadhunt_root.exists():
        raise FileNotFoundError(f"LeadHunt not found: {leadhunt_root}")
    sys.path.insert(0, str(leadhunt_root))

    from playwright.sync_api import sync_playwright  # noqa: PLC0415
    from app.parser.yandex_maps_parser import YandexMapsParser  # noqa: PLC0415
    from app.settings import browser_executable_path, browser_headless, browser_user_data_dir  # noqa: PLC0415

    with sync_playwright() as playwright:
        launch_options = {"headless": browser_headless()}
        executable_path = browser_executable_path()
        if executable_path:
            launch_options["executable_path"] = executable_path
        context_options = {
            "locale": "ru-RU",
            "timezone_id": "Asia/Novosibirsk",
            "viewport": {"width": 1440, "height": 1000},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        }
        user_data_dir = browser_user_data_dir()
        if user_data_dir:
            browser = None
            context = playwright.chromium.launch_persistent_context(user_data_dir=user_data_dir, **launch_options, **context_options)
        else:
            browser = playwright.chromium.launch(**launch_options)
            context = browser.new_context(**context_options)
        try:
            leads = YandexMapsParser().collect(context, args.city, args.niche, max(1, min(args.limit, 50)))
        finally:
            context.close()
            if browser is not None:
                browser.close()
    Path(args.output).write_text(json.dumps([asdict(lead) for lead in leads], ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
