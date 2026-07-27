from __future__ import annotations

import unittest
from pathlib import Path

from backend.jobs.adapters.base import format_salary, parse_salary_range
from backend.jobs.adapters.habr import HabrAdapter
from backend.jobs.adapters.hh import HhAdapter
from backend.jobs.adapters.telegram import TelegramAdapter
from backend.jobs.models import JobSettings, JobVacancy
from backend.jobs.scoring import score_vacancy


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jobs"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class SalaryHelperTests(unittest.TestCase):
    def test_parses_range_from_free_text(self) -> None:
        self.assertEqual((150000, 245000), parse_salary_range("150 000 - 245 000 ₽"))

    def test_parses_lower_bound_only(self) -> None:
        self.assertEqual((200000, None), parse_salary_range("от 200 000 ₽"))

    def test_ignores_small_numbers(self) -> None:
        self.assertEqual((None, None), parse_salary_range("опыт от 3 лет"))

    def test_formats_range_with_spaces(self) -> None:
        self.assertEqual("200 000 – 280 000 ₽", format_salary(200000, 280000, "RUR"))


class HhAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = HhAdapter()
        self.settings = JobSettings(keywords=("react",), telegram_channels=())

    def test_builds_official_api_url_with_area_and_limit(self) -> None:
        url = self.adapter.request_urls(JobSettings(keywords=("react", "vue"), area="Казань", per_source_limit=30))[0]

        self.assertIn("https://api.hh.ru/vacancies?", url)
        self.assertIn("area=88", url)
        self.assertIn("per_page=30", url)
        self.assertIn("react+OR+vue", url)

    def test_parses_vacancies_and_strips_highlight_markup(self) -> None:
        vacancies = self.adapter.parse(read_fixture("hh_vacancies.json"), self.settings)

        self.assertEqual(3, len(vacancies))
        first = vacancies[0]
        self.assertEqual("hh-121314151", first.external_id)
        self.assertEqual("Яндекс", first.company)
        self.assertEqual("Frontend-разработчик (React)", first.role)
        self.assertEqual(200000, first.salary_min)
        self.assertEqual(280000, first.salary_max)
        self.assertEqual("Москва", first.location)
        self.assertEqual("Удаленная работа", first.employment)
        self.assertNotIn("highlighttext", first.description)
        self.assertIn("React", first.tags)

    def test_keeps_vacancy_without_salary(self) -> None:
        vacancies = self.adapter.parse(read_fixture("hh_vacancies.json"), self.settings)

        intern = vacancies[2]
        self.assertIsNone(intern.salary_min)
        self.assertEqual("", intern.salary_text)


class HabrAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = HabrAdapter()
        self.settings = JobSettings(keywords=("react",), telegram_channels=())

    def test_parses_saved_cards(self) -> None:
        vacancies = self.adapter.parse(read_fixture("habr_vacancies.html"), self.settings)

        self.assertTrue(vacancies)
        first = vacancies[0]
        self.assertTrue(first.external_id.startswith("habr-"))
        self.assertTrue(first.role)
        self.assertTrue(first.company)
        self.assertTrue(first.url.startswith("https://career.habr.com/vacancies/"))
        self.assertTrue(first.published_at)

    def test_predicted_salary_does_not_become_a_numeric_offer(self) -> None:
        # Хабр показывает прогноз «похожие специалисты получают» — это не обещание работодателя.
        vacancies = self.adapter.parse(read_fixture("habr_vacancies.html"), self.settings)
        predicted = [item for item in vacancies if item.salary_text.startswith("≈")]

        self.assertTrue(predicted, "в фикстуре есть карточки с прогнозом зарплаты")
        for vacancy in predicted:
            self.assertIsNone(vacancy.salary_min)
            self.assertIsNone(vacancy.salary_max)

    def test_empty_markup_returns_no_vacancies(self) -> None:
        self.assertEqual([], self.adapter.parse("<html><body></body></html>", self.settings))


class TelegramAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = TelegramAdapter()
        self.settings = JobSettings(keywords=("node.js", "react"), telegram_channels=("forfrontend",))

    def test_builds_preview_urls_for_each_channel(self) -> None:
        urls = self.adapter.request_urls(JobSettings(telegram_channels=("@forfrontend", "jobs_hunt")))

        self.assertEqual(["https://t.me/s/forfrontend", "https://t.me/s/jobs_hunt"], urls)

    def test_parses_channel_posts_into_vacancies(self) -> None:
        vacancies = self.adapter.parse(read_fixture("telegram_channel.html"), self.settings)

        self.assertTrue(vacancies)
        first = vacancies[0]
        self.assertTrue(first.external_id.startswith("tg-forfrontend-"))
        self.assertTrue(first.url.startswith("https://t.me/forfrontend/"))
        self.assertEqual("Telegram · @forfrontend", first.employment)
        self.assertTrue(first.published_at)

    def test_decorative_emoji_line_is_not_used_as_the_title(self) -> None:
        html = (
            '<div class="tgme_widget_message" data-post="forfrontend/9">'
            '<div class="tgme_widget_message_text">🎙<br>Senior React Developer в Rooh Co.<br>'
            'Ищем разработчика в команду, удалённо, зарплата от 250 000 ₽</div></div>'
        )

        vacancies = self.adapter.parse(html, self.settings)

        self.assertEqual(1, len(vacancies))
        self.assertEqual("Senior React Developer", vacancies[0].role)
        # Завершающая точка отбрасывается вместе с обычной точкой конца предложения.
        self.assertEqual("Rooh Co", vacancies[0].company)

    def test_skips_short_posts_without_vacancy_markers(self) -> None:
        html = (
            '<div class="tgme_widget_message" data-post="forfrontend/1">'
            '<div class="tgme_widget_message_text">Всем привет</div></div>'
        )

        self.assertEqual([], self.adapter.parse(html, self.settings))


class ScoringTests(unittest.TestCase):
    def test_title_match_scores_higher_than_body_match(self) -> None:
        settings = JobSettings(keywords=("react",), excluded_keywords=(), telegram_channels=())
        in_title = JobVacancy(source="hh", external_id="1", company="A", role="React разработчик")
        in_body = JobVacancy(source="hh", external_id="2", company="B", role="Разработчик", description="стек React")

        self.assertGreater(score_vacancy(in_title, settings)[0], score_vacancy(in_body, settings)[0])

    def test_excluded_keyword_zeroes_the_score(self) -> None:
        settings = JobSettings(keywords=("react",), excluded_keywords=("стажёр",), telegram_channels=())
        vacancy = JobVacancy(source="hh", external_id="3", company="C", role="React стажёр")

        score, reasons, percent = score_vacancy(vacancy, settings)

        self.assertEqual(0, score)
        self.assertEqual(0, percent)
        self.assertIn("Стоп-слово «стажёр»", reasons)

    def test_stop_word_matches_regardless_of_yo(self) -> None:
        settings = JobSettings(keywords=("react",), excluded_keywords=("стажёр",), telegram_channels=())
        # Хабр Карьера пишет «Стажер», в настройках у пользователя «стажёр».
        vacancy = JobVacancy(source="habr", external_id="6", company="PREAX", role="Стажер Frontend-разработчик (React)")

        score, reasons, _ = score_vacancy(vacancy, settings)

        self.assertEqual(0, score)
        self.assertIn("Стоп-слово «стажёр»", reasons)

    def test_salary_above_threshold_adds_points(self) -> None:
        settings = JobSettings(keywords=("react",), excluded_keywords=(), telegram_channels=(), salary_min=150000)
        rich = JobVacancy(source="hh", external_id="4", company="D", role="React", salary_min=200000)
        poor = JobVacancy(source="hh", external_id="5", company="E", role="React")

        self.assertGreater(score_vacancy(rich, settings)[0], score_vacancy(poor, settings)[0])


if __name__ == "__main__":
    unittest.main()
