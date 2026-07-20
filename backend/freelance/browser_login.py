from __future__ import annotations

import sys

from .browser_profile import AUTH_URLS, PersistentBrowserSession


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else ""
    url = AUTH_URLS.get(source)
    if not url:
        return 2
    session = PersistentBrowserSession(source=source, headless=False)
    try:
        page = session.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        while page.context.pages:
            try:
                page.wait_for_timeout(500)
            except Exception:
                break
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
