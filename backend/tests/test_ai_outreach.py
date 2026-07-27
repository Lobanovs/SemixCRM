from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import httpx

from backend import database
from backend.ai import outreach
from backend.ai.client import AiClient, AiDisabledError, AiError, AiSettings, extract_json
from backend.ai.profile import ExecutorProfile, get_profile, init_profile_schema, save_profile
from backend.ai.prompts import build_client_message_prompt
from backend.ai.storage import init_ai_schema


CLIENT = {
    "id": 28,
    "name": "7R",
    "city": "Москва",
    "niche": "стоматологии",
    "address": "Семёновская набережная, 2/1 ст2",
    "phone": "+7 963 677-57-77",
    "website": "http://t.me/stom7r",
    "rating": 5.0,
    "reviews": 200,
    "branch_count": None,
    "pain": "Есть канал для контакта, но нет сайта — хороший кандидат для первого сообщения.",
    "lead_score": 19,
    "match_score": 83,
    "lead_score_reasons": ["Нет сайта +5", "Больше 30 отзывов +3"],
    "contacts": [
        {"type": "whatsapp", "url": "https://wa.me/79636775777", "value": "https://wa.me/79636775777?text=2gis"},
        {"type": "telegram", "url": "https://t.me/stom7r", "value": "https://t.me/stom7r"},
        {"type": "phone", "url": "+7 963 677-57-77", "value": "+7 963 677-57-77"},
    ],
}

GOOD_ANSWER = {
    "analysis": "Клиника с рейтингом 5,0 и 200 отзывами, но вместо сайта только Telegram-канал. "
                "Поток пациентов есть, а записаться онлайн негде — заявки уходят к соседям.",
    "pain": "Пациенты находят клинику, но не могут записаться без звонка и уходят к конкурентам",
    "money_argument": "Даже два-три несостоявшихся импланта в месяц — это сотни тысяч рублей; "
                      "оценка приблизительная, но порядок такой.",
    "variants": [
        {
            "angle": "наблюдение о них",
            "text": "Добрый день! Посмотрел вашу карточку в 2ГИС: рейтинг 5,0 и двести отзывов — "
                    "для стоматологии это редкость. При этом записаться можно только звонком, "
                    "сайта нет. Часть людей, которые вас нашли вечером или в выходной, до звонка "
                    "просто не доходят. Могу за три минуты показать на экране, где именно теряются "
                    "заявки. Прислать разбор? Семён",
        },
        {
            "angle": "деньги",
            "text": "Здравствуйте! У вас двести отзывов и рейтинг 5,0 — пациенты вас любят. "
                    "Но записаться онлайн негде, и те, кто ищет ночью, уходят туда, где есть кнопка "
                    "записи. Даже пара таких человек в месяц при чеке на имплант — заметные деньги. "
                    "Хотите, покажу короткий разбор, что можно поправить за неделю? Семён",
        },
        {
            "angle": "короткий",
            "text": "Добрый день! Нашёл вас в 2ГИС — рейтинг 5,0, а сайта нет, только Telegram. "
                    "Похоже, часть заявок теряется по вечерам. Сделать бесплатный трёхминутный "
                    "видеоразбор? Семён",
        },
    ],
    "follow_up": "Добрый день! Разбор всё ещё в силе, если интересно — пришлю сегодня.",
}


def response_with(payload: object, status: int = 200) -> httpx.Response:
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": body}}]},
        request=httpx.Request("POST", "https://opencode.ai/zen/go/v1/chat/completions"),
    )


class RecordingTransport:
    """Подменяет сеть: живые вызовы стоят денег и делают тесты нестабильными."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers) or [GOOD_ANSWER]
        self.calls: list[dict] = []

    def __call__(self, payload: dict) -> httpx.Response:
        self.calls.append(payload)
        answer = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(answer, httpx.Response):
            return answer
        return response_with(answer)

    @property
    def last_user_prompt(self) -> str:
        return self.calls[-1]["messages"][1]["content"]

    @property
    def last_system_prompt(self) -> str:
        return self.calls[-1]["messages"][0]["content"]


def client_for(transport: RecordingTransport) -> AiClient:
    return AiClient(AiSettings(api_key="test-key", model="test-model"), transport=transport)


class PromptTests(unittest.TestCase):
    def test_prompt_carries_the_real_facts_of_the_card(self) -> None:
        prompt = build_client_message_prompt(CLIENT, ExecutorProfile())

        for fact in ("7R", "Москва", "стоматологии", "5.0", "200", "Нет сайта +5"):
            self.assertIn(fact, prompt, fact)
        self.assertIn("Полноценный сайт: нет", prompt)
        self.assertIn("whatsapp", prompt)

    def test_prompt_includes_who_is_writing(self) -> None:
        profile = ExecutorProfile(name="Семён", price_from="от 35 000 ₽", offer="бесплатный видеоразбор")

        prompt = build_client_message_prompt(CLIENT, profile)

        self.assertIn("от 35 000 ₽", prompt)
        self.assertIn("бесплатный видеоразбор", prompt)

    def test_telegram_link_is_not_counted_as_a_real_site(self) -> None:
        self.assertIn("Полноценный сайт: нет", build_client_message_prompt(CLIENT, ExecutorProfile()))
        with_site = {**CLIENT, "website": "https://7r-clinic.ru"}
        self.assertIn("Полноценный сайт: да", build_client_message_prompt(with_site, ExecutorProfile()))

    def test_missing_data_is_marked_instead_of_invented(self) -> None:
        bare = {**CLIENT, "rating": None, "reviews": None, "address": "", "lead_score_reasons": []}

        prompt = build_client_message_prompt(bare, ExecutorProfile())

        self.assertIn("Рейтинг: нет данных", prompt)
        self.assertIn("Отзывов: нет данных", prompt)
        self.assertNotIn("Почему лид интересен", prompt)

    def test_niche_economics_are_offered_as_an_estimate(self) -> None:
        prompt = build_client_message_prompt(CLIENT, ExecutorProfile())

        self.assertIn("имплант", prompt)
        self.assertIn("не факты о компании", prompt)


class JsonExtractionTests(unittest.TestCase):
    def test_plain_json(self) -> None:
        self.assertEqual({"a": 1}, extract_json('{"a": 1}'))

    def test_fenced_json(self) -> None:
        self.assertEqual({"a": 1}, extract_json('```json\n{"a": 1}\n```'))

    def test_json_with_prose_around_it(self) -> None:
        self.assertEqual({"a": 1}, extract_json('Конечно! Вот результат:\n{"a": 1}\nГотово.'))

    def test_answer_without_json_is_an_error(self) -> None:
        with self.assertRaises(AiError):
            extract_json("Извините, не могу помочь")


class GenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(database, "DB_PATH", Path(self.temp_dir.name) / "ai.sqlite3")
        self.path_patch.start()
        database.init_db()
        init_profile_schema()
        init_ai_schema()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_generates_three_variants_with_analysis_and_follow_up(self) -> None:
        transport = RecordingTransport()

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(3, len(result["variants"]))
        self.assertTrue(result["analysis"])
        self.assertTrue(result["pain"])
        self.assertTrue(result["follow_up"])
        self.assertFalse(result["cached"])
        self.assertEqual([], result["warnings"])

    def test_whatsapp_link_carries_the_message_text(self) -> None:
        transport = RecordingTransport()

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        # WhatsApp должен быть первым: только он подставляет текст в диалог.
        self.assertEqual("WhatsApp", result["links"][0]["channel"])
        whatsapp = result["links"][0]
        self.assertTrue(whatsapp["url"].startswith("https://wa.me/79636775777?text="))
        self.assertIn(quote("рейтинг 5,0")[:20], whatsapp["url"])

    def test_second_call_is_served_from_cache(self) -> None:
        transport = RecordingTransport()

        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))
        second = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(1, len(transport.calls), "повторная генерация не должна дёргать модель")
        self.assertTrue(second["cached"])
        self.assertEqual(3, len(second["variants"]))

    def test_force_regenerates_even_with_a_cached_result(self) -> None:
        transport = RecordingTransport()
        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        outreach.generate_client_message(CLIENT, force=True, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))

    def test_changed_client_data_invalidates_the_cache(self) -> None:
        transport = RecordingTransport()
        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        outreach.generate_client_message({**CLIENT, "reviews": 400}, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))

    def test_changed_profile_invalidates_the_cache(self) -> None:
        transport = RecordingTransport()
        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        save_profile(ExecutorProfile(price_from="от 90 000 ₽"))
        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))
        self.assertIn("от 90 000 ₽", transport.last_user_prompt)

    def test_markdown_and_links_are_stripped_from_the_message(self) -> None:
        dirty = {
            **GOOD_ANSWER,
            "variants": [{
                "angle": "**жирный**",
                "text": "Добрый день! Посмотрел карточку — рейтинг высокий, а сайта нет. "
                        "Подробности тут https://example.com/promo и в **портфолио**. "
                        "Показать короткий разбор, где теряются заявки? Семён",
            }],
        }
        transport = RecordingTransport(dirty)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        text = result["variants"][0]["text"]
        self.assertNotIn("https://", text)
        self.assertNotIn("**", text)
        self.assertNotIn("**", result["variants"][0]["angle"])

    def test_removing_a_link_does_not_leave_orphaned_punctuation(self) -> None:
        # Жадный шаблон ссылки съедал закрывающую скобку, и оставалось «сайта нет (».
        with_link = {
            **GOOD_ANSWER,
            "analysis": "Клиника сильная, но полноценного сайта нет (http://t.me/stom7r). Заявки теряются вечером.",
        }
        transport = RecordingTransport(with_link)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(
            "Клиника сильная, но полноценного сайта нет. Заявки теряются вечером.",
            result["analysis"],
        )

    def test_spam_phrases_are_reported_as_warnings(self) -> None:
        spammy = {
            **GOOD_ANSWER,
            "variants": [{
                "angle": "шаблон",
                "text": "Здравствуйте! Меня зовут Семён, у меня для вас уникальное предложение: "
                        "сайты под ключ от команды профессионалов с индивидуальным подходом. "
                        "Хотите узнать больше о наших услугах и ценах на разработку? Семён",
            }],
        }
        transport = RecordingTransport(spammy)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertTrue(result["warnings"])
        self.assertIn("меня зовут", " ".join(result["warnings"]).casefold())

    def test_too_short_variants_are_dropped(self) -> None:
        mixed = {**GOOD_ANSWER, "variants": [{"angle": "обрывок", "text": "Привет!"}, GOOD_ANSWER["variants"][0]]}
        transport = RecordingTransport(mixed)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(1, len(result["variants"]))
        self.assertIn("слишком короткий", " ".join(result["warnings"]))

    def test_answer_without_usable_variants_is_an_error(self) -> None:
        transport = RecordingTransport({**GOOD_ANSWER, "variants": []})

        with self.assertRaises(AiError):
            outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

    def test_broken_json_is_retried_once_and_then_succeeds(self) -> None:
        transport = RecordingTransport("это не json", GOOD_ANSWER)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))
        self.assertEqual(3, len(result["variants"]))
        self.assertIn("ТОЛЬКО валидный JSON", transport.last_user_prompt)

    def test_generation_without_a_key_is_refused_cleanly(self) -> None:
        disabled = AiClient(AiSettings(api_key=""), transport=RecordingTransport())

        with self.assertRaises(AiDisabledError):
            outreach.generate_client_message(CLIENT, ai_client=disabled)

    def test_profile_defaults_survive_an_empty_save(self) -> None:
        save_profile(ExecutorProfile(name="", signature=""))

        stored = get_profile()

        self.assertEqual("Семён", stored.name)
        self.assertTrue(stored.offer)


class ApiErrorTests(unittest.TestCase):
    def _failing(self, status: int) -> AiClient:
        def transport(_payload: dict) -> httpx.Response:
            return httpx.Response(status, text="nope", request=httpx.Request("POST", "https://opencode.ai"))
        return AiClient(AiSettings(api_key="k"), transport=transport)

    def test_rejected_key_is_explained(self) -> None:
        with self.assertRaises(AiError) as error:
            self._failing(401).complete("s", "u")
        self.assertIn("401", str(error.exception))

    def test_rate_limit_is_explained(self) -> None:
        with self.assertRaises(AiError) as error:
            self._failing(429).complete("s", "u")
        self.assertIn("429", str(error.exception))

    def test_network_failure_is_wrapped(self) -> None:
        def transport(_payload: dict) -> httpx.Response:
            raise httpx.ConnectError("нет сети")
        with self.assertRaises(AiError):
            AiClient(AiSettings(api_key="k"), transport=transport).complete("s", "u")


if __name__ == "__main__":
    unittest.main()
