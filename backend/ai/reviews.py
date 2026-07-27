from __future__ import annotations

import ast
import json
import logging
import re
from html import unescape
from typing import Any

import httpx
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)

FIRM_URL = re.compile(
    r"^https://(?:www\.)?2gis\.ru/(?:[^/?#]+/)?firm/(\d+)(?:[/?#]|$)",
    re.IGNORECASE,
)
REACT_QUERY_STATE = re.compile(
    r"var\s+__REACT_QUERY_STATE__\s*=\s*JSON\.parse\('((?:\\.|[^'])*)'\);",
    re.DOTALL,
)
USER_AGENT = "SemixCRM/1.0 (+local review assistant)"
MAX_RESPONSE_BYTES = 2_000_000
MAX_REVIEWS = 7
MAX_REVIEW_LENGTH = 600
MIN_REVIEW_LENGTH = 35


def _clean_review_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < MIN_REVIEW_LENGTH:
        return ""
    if len(text) <= MAX_REVIEW_LENGTH:
        return text
    clipped = text[:MAX_REVIEW_LENGTH].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return f"{clipped}…"


def _decode_react_query_state(script: str) -> dict[str, Any]:
    match = REACT_QUERY_STATE.search(script)
    if match is None:
        return {}
    decoded = ast.literal_eval("'" + match.group(1) + "'")
    payload = json.loads(decoded)
    return payload if isinstance(payload, dict) else {}


def _review_texts(state: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for query in state.get("queries") or []:
        if not isinstance(query, dict):
            continue
        query_key = query.get("queryKey") or []
        if not isinstance(query_key, list) or not query_key or query_key[0] != "fetchEntityReviews":
            continue
        pages = query.get("state", {}).get("data", {}).get("pages", [])
        for page in pages if isinstance(pages, list) else []:
            if not isinstance(page, dict):
                continue
            for item in page.get("items") or []:
                if not isinstance(item, dict) or item.get("is_hidden"):
                    continue
                text = _clean_review_text(item.get("text"))
                if text and text not in texts:
                    texts.append(text)
                if len(texts) >= MAX_REVIEWS:
                    return texts
    return texts


def fetch_2gis_review_evidence(
    card_url: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[dict[str, str]]:
    """Return a small, numbered set of public reviews from a trusted 2GIS card."""

    match = FIRM_URL.match(str(card_url or "").strip())
    if match is None:
        return []

    url = f"https://2gis.ru/firm/{match.group(1)}/tab/reviews"
    try:
        with httpx.Client(
            transport=transport,
            follow_redirects=True,
            timeout=8,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            logger.warning("2GIS review page is too large for branch %s", match.group(1))
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        script = next(
            node.get_text()
            for node in soup.find_all("script")
            if "fetchEntityReviews" in node.get_text()
        )
        texts = _review_texts(_decode_react_query_state(script))
    except (StopIteration, AttributeError, TypeError, ValueError, SyntaxError, httpx.HTTPError) as error:
        logger.info("2GIS reviews are unavailable for branch %s: %s", match.group(1), error)
        return []

    return [{"id": f"R{index}", "text": text} for index, text in enumerate(texts, 1)]
