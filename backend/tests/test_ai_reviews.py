from __future__ import annotations

import unittest
from pathlib import Path

import httpx

from backend.ai.reviews import fetch_2gis_review_evidence


FIXTURE = Path(__file__).parent / "fixtures" / "ai" / "2gis_reviews_page.html"


class ReviewEvidenceTests(unittest.TestCase):
    def test_extracts_numbered_customer_reviews_from_react_query_state(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text=FIXTURE.read_text(encoding="utf-8"),
                request=request,
            )
        )

        result = fetch_2gis_review_evidence(
            "https://2gis.ru/firm/70000001042303479",
            transport=transport,
        )

        self.assertEqual(["R1", "R2", "R3"], [item["id"] for item in result])
        self.assertIn("косметолог Анна", result[1]["text"])
        self.assertEqual(1, sum("приятная и спокойная атмосфера" in item["text"] for item in result))
        self.assertTrue(all(len(item["text"]) >= 35 for item in result))

    def test_rejects_untrusted_url_without_request(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, text="", request=request)

        result = fetch_2gis_review_evidence(
            "https://example.com/firm/70000001042303479",
            transport=httpx.MockTransport(handler),
        )

        self.assertEqual([], result)
        self.assertEqual([], calls)

    def test_network_failure_returns_empty_evidence(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline", request=request)

        result = fetch_2gis_review_evidence(
            "https://2gis.ru/firm/70000001042303479",
            transport=httpx.MockTransport(handler),
        )

        self.assertEqual([], result)

    def test_uses_an_identifiable_client_user_agent(self) -> None:
        seen_user_agents: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_user_agents.append(request.headers.get("user-agent", ""))
            return httpx.Response(
                200,
                text=FIXTURE.read_text(encoding="utf-8"),
                request=request,
            )

        fetch_2gis_review_evidence(
            "https://2gis.ru/firm/70000001042303479",
            transport=httpx.MockTransport(handler),
        )

        self.assertEqual(["SemixCRM/1.0 (+local review assistant)"], seen_user_agents)


if __name__ == "__main__":
    unittest.main()
