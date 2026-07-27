from __future__ import annotations

import unittest
from pathlib import Path

from backend.jobs.adapters.base import is_developer_role
from backend.jobs.adapters.remote import (
    RemoteOkAdapter,
    RemotiveAdapter,
    WeWorkRemotelyAdapter,
    parse_usd_range,
)
from backend.jobs.models import JOB_SOURCES, TELEGRAM_JOB_CHANNELS, JobSettings
from backend.jobs.scoring import score_vacancy


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jobs"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class DeveloperRoleFilterTests(unittest.TestCase):
    def test_developer_titles_pass(self) -> None:
        for role in ("Senior React Developer", "Frontend Engineer", "Python-разработчик", "Верстальщик"):
            self.assertTrue(is_developer_role(role), role)

    def test_non_developer_titles_are_rejected(self) -> None:
        for role in ("Business Development Manager", "Data Entry Specialist", "Concept Artist",
                     "OFFICE ASSISTANT", "Менеджер по продажам", "Content Reviewer"):
            self.assertFalse(is_developer_role(role), role)

    def test_tags_alone_do_not_make_a_vacancy_technical(self) -> None:
        # RemoteOK вешает react и python на каждую вакансию — по тегам судить нельзя.
        self.assertFalse(is_developer_role("Concept Artist"))

    def test_fallback_is_used_only_when_asked(self) -> None:
        post = "Ищем разработчика на React в продуктовую команду, удалённо"
        self.assertFalse(is_developer_role("Вакансия дня"))
        self.assertTrue(is_developer_role("Вакансия дня", post))


class UsdSalaryTests(unittest.TestCase):
    def test_parses_k_shorthand(self) -> None:
        self.assertEqual((30000, 100000), parse_usd_range("$30k - $100k"))

    def test_parses_full_numbers_with_commas(self) -> None:
        self.assertEqual((120000, 150000), parse_usd_range("$120,000 — $150,000"))

    def test_single_amount_becomes_lower_bound(self) -> None:
        self.assertEqual((90, None), parse_usd_range("from $90 /hour"))

    def test_text_without_amounts(self) -> None:
        self.assertEqual((None, None), parse_usd_range("Competitive salary"))


class RemoteOkAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = RemoteOkAdapter()
        self.settings = JobSettings(keywords=("react", "vue"), telegram_channels=())

    def test_one_request_per_keyword(self) -> None:
        urls = self.adapter.request_urls(self.settings)

        self.assertEqual(2, len(urls))
        self.assertTrue(all(url.startswith("https://remoteok.com/api?tags=") for url in urls))

    def test_legal_header_element_is_not_a_vacancy(self) -> None:
        vacancies = self.adapter.parse(read("remoteok_jobs.json"), self.settings)

        self.assertTrue(all(vacancy.role for vacancy in vacancies))
        self.assertTrue(all(vacancy.external_id.startswith("remoteok-") for vacancy in vacancies))

    def test_only_developer_roles_survive(self) -> None:
        vacancies = self.adapter.parse(read("remoteok_jobs.json"), self.settings)

        for vacancy in vacancies:
            self.assertTrue(is_developer_role(vacancy.role), vacancy.role)
            self.assertEqual("USD", vacancy.currency)


class RemotiveAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = RemotiveAdapter()
        self.settings = JobSettings(keywords=("react",), telegram_channels=(), per_source_limit=30)

    def test_builds_search_url_with_limit(self) -> None:
        url = self.adapter.request_urls(self.settings)[0]

        self.assertIn("remotive.com/api/remote-jobs?", url)
        self.assertIn("limit=30", url)
        self.assertIn("search=react", url)

    def test_parses_jobs_and_keeps_original_salary_text(self) -> None:
        vacancies = self.adapter.parse(read("remotive_jobs.json"), self.settings)

        self.assertTrue(vacancies)
        for vacancy in vacancies:
            self.assertTrue(vacancy.external_id.startswith("remotive-"))
            self.assertEqual("USD", vacancy.currency)
            self.assertTrue(vacancy.url.startswith("https://remotive.com/"))


class WeWorkRemotelyAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = WeWorkRemotelyAdapter()
        self.settings = JobSettings(keywords=("react",), telegram_channels=())

    def test_reads_link_from_guid(self) -> None:
        # html.parser считает <link> пустым тегом, поэтому ссылка берётся из guid.
        vacancies = self.adapter.parse(read("wwr_programming.rss"), self.settings)

        self.assertTrue(vacancies)
        for vacancy in vacancies:
            self.assertTrue(vacancy.url.startswith("https://weworkremotely.com/remote-jobs/"), vacancy.url)

    def test_splits_company_and_role_from_the_title(self) -> None:
        vacancies = self.adapter.parse(read("wwr_programming.rss"), self.settings)

        for vacancy in vacancies:
            self.assertTrue(vacancy.company)
            self.assertNotIn(":", vacancy.company)
            self.assertTrue(vacancy.role)

    def test_empty_feed_gives_no_vacancies(self) -> None:
        self.assertEqual([], self.adapter.parse("<rss><channel></channel></rss>", self.settings))

    def test_no_invented_salary_from_the_description(self) -> None:
        # В описаниях WWR попадаются часовые ставки и случайные суммы в долларах.
        vacancies = self.adapter.parse(read("wwr_programming.rss"), self.settings)

        for vacancy in vacancies:
            self.assertIsNone(vacancy.salary_min, vacancy.role)
            self.assertIsNone(vacancy.salary_max, vacancy.role)
            self.assertEqual("", vacancy.salary_text)


class CurrencyScoringTests(unittest.TestCase):
    def test_currency_pay_is_rewarded_without_the_rouble_threshold(self) -> None:
        settings = JobSettings(keywords=("react",), telegram_channels=(), salary_min=250000)
        vacancies = RemotiveAdapter().parse(read("remotive_jobs.json"), settings)
        self.assertTrue(vacancies)

        _, reasons, _ = score_vacancy(vacancies[0], settings)

        self.assertIn("Оплата в валюте (USD)", " ".join(reasons))


class SourceCatalogueTests(unittest.TestCase):
    def test_all_registered_sources_have_an_adapter(self) -> None:
        from backend.jobs.adapters.registry import adapter_registry

        self.assertEqual(set(JOB_SOURCES), set(adapter_registry()))

    def test_telegram_defaults_are_a_deduplicated_list(self) -> None:
        self.assertGreaterEqual(len(TELEGRAM_JOB_CHANNELS), 30)
        self.assertEqual(len(set(TELEGRAM_JOB_CHANNELS)), len(TELEGRAM_JOB_CHANNELS))
        for channel in TELEGRAM_JOB_CHANNELS:
            self.assertNotIn("@", channel)
            self.assertEqual(channel, channel.strip().lower())


if __name__ == "__main__":
    unittest.main()
