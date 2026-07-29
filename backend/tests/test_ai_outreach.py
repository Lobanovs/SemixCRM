from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import quote

import httpx

from backend import database, main
from backend.ai import outreach, storage
from backend.ai.client import AiClient, AiDisabledError, AiError, AiSettings, extract_json
from backend.ai.profile import ExecutorProfile, get_profile, init_profile_schema, save_profile
from backend.ai.prompts import SYSTEM_PROMPT, build_client_message_prompt
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
    "analysis": {
        "signal": "Рейтинг 5,0 и 200 отзывов показывают сильное доверие к клинике.",
        "problem": "Неясно, как пациенты узнают цены и записываются после просмотра карточки.",
        "opportunity": "Ответ владельца покажет, есть ли разрыв в текущем процессе.",
    },
    "review_insight": {"summary": "", "evidence_ids": []},
    "variants": [
        {
            "tone": "confident",
            "title": "Цены и информация",
            "text": (
                "Здравствуйте! Увидел, что в карточке 2GIS не указан отдельный сайт "
                "с услугами и ценами. Пациенты уточняют стоимость у администратора "
                "или у вас есть отдельный прайс?"
            ),
        },
        {
            "tone": "hard_sell",
            "title": "Запись и заявки",
            "text": (
                "Здравствуйте! В карточке 7R вижу телефон и Telegram, но не вижу "
                "онлайн-записи. Пациенты записываются сообщением администратору "
                "или через другую систему?"
            ),
        },
        {
            "tone": "expert",
            "title": "Обработка обращений",
            "text": (
                "Здравствуйте! У 7R высокий рейтинг и 200 отзывов, а из быстрых "
                "контактов вижу Telegram. Кто отвечает пациентам, если они пишут "
                "вечером или администратор занят?"
            ),
        },
    ],
    "follow_up": "",
}

REVIEW_EVIDENCE = [
    {"id": "R1", "text": "Прекрасная студия, косметолог Анна качественно проводит процедуры."},
    {"id": "R2", "text": "Очень приятная атмосфера, мастера внимательные и умеют найти подход."},
]

REVIEW_ANSWER = {
    **GOOD_ANSWER,
    "review_insight": {
        "summary": "Клиенты особенно отмечают косметолога Анну, спокойную атмосферу и внимательное отношение.",
        "evidence_ids": ["R1", "R2"],
    },
    "variants": [
        {
            **GOOD_ANSWER["variants"][0],
            "text": (
                "Здравствуйте! Почитал отзывы 2GIS: клиенты особенно отмечают "
                "косметолога Анну и внимательное отношение. Новые пациенты чаще "
                "записываются по рекомендации или через администратора?"
            ),
        },
        GOOD_ANSWER["variants"][1],
        GOOD_ANSWER["variants"][2],
    ],
}


def response_with(payload: object, status: int = 200) -> httpx.Response:
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": body}}]},
        request=httpx.Request("POST", "https://opencode.ai/zen/go/v1/chat/completions"),
    )


def completion_response(
    content: Any,
    *,
    finish_reason: str = "stop",
    reasoning: str | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{
                "finish_reason": finish_reason,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": reasoning,
                },
            }],
        },
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

        self.assertIn("Имя отправителя: Семён", prompt)
        self.assertNotIn("от 35 000 ₽", prompt)
        self.assertNotIn("бесплатный видеоразбор", prompt)

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

    def test_sales_profile_and_economics_are_not_exposed_to_the_first_contact_prompt(self) -> None:
        prompt = build_client_message_prompt(
            CLIENT,
            ExecutorProfile(
                name="Семён",
                price_from="от 90 000 ₽",
                portfolio_url="https://example.com/portfolio",
            ),
        )

        self.assertIn("Имя отправителя: Семён", prompt)
        self.assertNotIn("90 000", prompt)
        self.assertNotIn("example.com/portfolio", prompt)
        self.assertNotIn("имплант", prompt)

    def test_prompt_requires_consultative_first_contact(self) -> None:
        for tone in ("confident", "hard_sell", "expert"):
            self.assertIn(tone, SYSTEM_PROMPT)
        for title in ("Цены и информация", "Запись и заявки", "Обработка обращений"):
            self.assertIn(title, SYSTEM_PROMPT)
        self.assertIn("70–260 символов", SYSTEM_PROMPT)
        self.assertIn("Ровно один вопросительный знак", SYSTEM_PROMPT)
        self.assertIn("Предлагать сайт", SYSTEM_PROMPT)
        self.assertIn("в карточке 2GIS не увидел отдельного сайта", SYSTEM_PROMPT)
        self.assertIn("evidence_ids", SYSTEM_PROMPT)

    def test_prompt_contains_review_evidence_and_manual_observation(self) -> None:
        prompt = build_client_message_prompt(
            CLIENT,
            ExecutorProfile(),
            manual_observation="На сайте нельзя оставить заявку",
            review_evidence=REVIEW_EVIDENCE,
        )

        self.assertIn("РУЧНОЕ НАБЛЮДЕНИЕ", prompt)
        self.assertIn("На сайте нельзя оставить заявку", prompt)
        self.assertIn("[R1]", prompt)
        self.assertIn("косметолог Анна", prompt)


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


class AiClientTests(unittest.TestCase):
    def test_structured_mimo_request_disables_thinking_and_asks_for_json(self) -> None:
        transport = RecordingTransport({"ok": True})
        client = AiClient(
            AiSettings(api_key="test-key", model="mimo-v2.5-pro"),
            transport=transport,
        )

        self.assertEqual({"ok": True}, client.complete_json("system", "user"))

        self.assertEqual({"type": "json_object"}, transport.calls[0]["response_format"])
        self.assertEqual(
            {"enable_thinking": False},
            transport.calls[0]["chat_template_kwargs"],
        )

    def test_non_mimo_request_does_not_send_mimo_template_settings(self) -> None:
        transport = RecordingTransport("Готово")
        client = AiClient(
            AiSettings(api_key="test-key", model="glm-5.2"),
            transport=transport,
        )

        client.complete("system", "user")

        self.assertNotIn("chat_template_kwargs", transport.calls[0])

    def test_reasoning_only_length_response_is_not_converted_to_none(self) -> None:
        transport = RecordingTransport(completion_response(
            None,
            finish_reason="length",
            reasoning="Long private chain of thought",
        ))
        client = AiClient(
            AiSettings(api_key="test-key", model="mimo-v2.5-pro"),
            transport=transport,
        )

        with self.assertRaises(AiError) as error:
            client.complete("system", "user")

        self.assertIn("лимит ответа ушёл на внутреннее рассуждение", str(error.exception))
        self.assertNotIn("None", str(error.exception))

    def test_structural_validation_error_is_repaired_once(self) -> None:
        transport = RecordingTransport({"variants": []}, {"variants": [{"tone": "confident"}]})
        client = AiClient(
            AiSettings(api_key="test-key", model="glm-5.2"),
            transport=transport,
        )

        def validate(payload: dict[str, Any]) -> None:
            if not payload["variants"]:
                raise AiError("нет обязательных вариантов")

        result = client.complete_json("system", "user", validate=validate)

        self.assertEqual([{"tone": "confident"}], result["variants"])
        self.assertEqual(2, len(transport.calls))
        self.assertIn("нет обязательных вариантов", transport.last_user_prompt)


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

    def test_generates_three_consultative_questions_with_analysis(self) -> None:
        transport = RecordingTransport()

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(3, len(result["variants"]))
        self.assertEqual(
            ["confident", "hard_sell", "expert"],
            [item["tone"] for item in result["variants"]],
        )
        self.assertEqual("Цены и информация", result["variants"][0]["title"])
        self.assertTrue(result["analysis"])
        self.assertTrue(result["pain"])
        self.assertEqual("", result["follow_up"])
        self.assertTrue(all(item["text"].count("?") == 1 for item in result["variants"]))
        self.assertTrue(all(item["text"].endswith("?") for item in result["variants"]))
        self.assertFalse(result["cached"])
        self.assertEqual([], result["review_evidence"])
        self.assertEqual("https://semyon-lobanov-portfolio.vercel.app/", result["portfolio_url"])
        self.assertEqual([], result["warnings"])

    def test_prompt_version_invalidates_legacy_cached_results(self) -> None:
        self.assertEqual(7, outreach.build_input(CLIENT, get_profile())["prompt_version"])

    def test_grounded_review_summary_keeps_its_evidence_ids(self) -> None:
        client = {**CLIENT, "card_url": "https://2gis.ru/firm/70000001098575869"}
        transport = RecordingTransport(REVIEW_ANSWER)

        result = outreach.generate_client_message(
            client,
            ai_client=client_for(transport),
            review_loader=lambda _url: REVIEW_EVIDENCE,
        )

        self.assertEqual(["R1", "R2"], result["review_insight"]["evidence_ids"])
        self.assertEqual(REVIEW_EVIDENCE, result["review_evidence"])
        self.assertIn("Почитал отзывы", result["variants"][0]["text"])
        self.assertEqual([], result["warnings"])
        self.assertIn("[R1]", transport.last_user_prompt)

    def test_review_evidence_does_not_force_review_word_into_first_question(self) -> None:
        client = {**CLIENT, "card_url": "https://2gis.ru/firm/70000001098575869"}
        answer = {
            **GOOD_ANSWER,
            "review_insight": REVIEW_ANSWER["review_insight"],
        }
        transport = RecordingTransport(answer)

        result = outreach.generate_client_message(
            client,
            ai_client=client_for(transport),
            review_loader=lambda _url: REVIEW_EVIDENCE,
        )

        self.assertEqual(1, len(transport.calls))
        self.assertIn("отдельный прайс", result["variants"][0]["text"])
        self.assertEqual(["R1", "R2"], result["review_insight"]["evidence_ids"])

    def test_unsupported_review_ids_trigger_one_repair(self) -> None:
        invalid = {
            **REVIEW_ANSWER,
            "review_insight": {
                "summary": "Клиенты хвалят несуществующего специалиста",
                "evidence_ids": ["R9"],
            },
        }
        client = {**CLIENT, "card_url": "https://2gis.ru/firm/70000001098575869"}
        transport = RecordingTransport(invalid, REVIEW_ANSWER)

        result = outreach.generate_client_message(
            client,
            ai_client=client_for(transport),
            review_loader=lambda _url: REVIEW_EVIDENCE,
        )

        self.assertEqual(2, len(transport.calls))
        self.assertEqual(["R1", "R2"], result["review_insight"]["evidence_ids"])
        self.assertIn("R9", transport.last_user_prompt)

    def test_review_failure_falls_back_with_a_warning(self) -> None:
        client = {**CLIENT, "card_url": "https://2gis.ru/firm/70000001098575869"}

        result = outreach.generate_client_message(
            client,
            ai_client=client_for(RecordingTransport()),
            review_loader=lambda _url: [],
        )

        self.assertEqual([], result["review_evidence"])
        self.assertEqual({"summary": "", "evidence_ids": []}, result["review_insight"])
        self.assertTrue(any("Отзывы 2GIS" in warning for warning in result["warnings"]))

    def test_manual_observation_is_sent_and_invalidates_cache(self) -> None:
        transport = RecordingTransport()

        outreach.generate_client_message(
            CLIENT,
            manual_observation="На сайте нет формы записи",
            ai_client=client_for(transport),
        )
        outreach.generate_client_message(
            CLIENT,
            manual_observation="На сайте сложно найти цены",
            ai_client=client_for(transport),
        )

        self.assertEqual(2, len(transport.calls))
        self.assertIn("На сайте сложно найти цены", transport.last_user_prompt)

    def test_api_forwards_trimmed_manual_observation(self) -> None:
        with (
            patch.object(main, "list_clients", return_value=[CLIENT]),
            patch.object(
                main,
                "generate_client_message",
                return_value={"cached": False, "variants": []},
            ) as generate,
        ):
            response = main.ai_client_message(
                28,
                request=main.AiMessageRequest(
                    manual_observation="  На сайте нет формы записи  "
                ),
                force=False,
            )

        self.assertTrue(response["ready"])
        generate.assert_called_once_with(
            CLIENT,
            force=False,
            manual_observation="На сайте нет формы записи",
        )

    def test_storage_lists_latest_results_with_generation_context(self) -> None:
        payload = {
            **GOOD_ANSWER,
            "manual_observation": "Запись только по телефону",
            "review_evidence": REVIEW_EVIDENCE,
        }
        fingerprint = storage.input_hash(
            outreach.build_input(
                CLIENT,
                get_profile(),
                payload["manual_observation"],
                REVIEW_EVIDENCE,
            )
        )
        storage.save_result(
            "client_message",
            "client",
            CLIENT["id"],
            fingerprint,
            "mimo-v2.5-pro",
            payload,
        )

        latest = storage.list_latest("client_message", "client")

        self.assertEqual({CLIENT["id"]}, set(latest))
        self.assertEqual(fingerprint, latest[CLIENT["id"]]["input_hash"])
        self.assertEqual("Запись только по телефону", latest[CLIENT["id"]]["payload"]["manual_observation"])
        self.assertEqual(REVIEW_EVIDENCE, latest[CLIENT["id"]]["payload"]["review_evidence"])

    def test_clients_report_ready_stale_and_missing_ai_message_statuses(self) -> None:
        stale_client = {**CLIENT, "id": 29, "name": "Старая карточка", "reviews": 400}
        missing_client = {**CLIENT, "id": 30, "name": "Без текста"}
        profile = get_profile()
        ready_payload = {
            **GOOD_ANSWER,
            "manual_observation": "Запись только по телефону",
            "review_evidence": REVIEW_EVIDENCE,
        }
        storage.save_result(
            "client_message",
            "client",
            CLIENT["id"],
            storage.input_hash(
                outreach.build_input(
                    CLIENT,
                    profile,
                    ready_payload["manual_observation"],
                    REVIEW_EVIDENCE,
                )
            ),
            "mimo-v2.5-pro",
            ready_payload,
        )
        storage.save_result(
            "client_message",
            "client",
            stale_client["id"],
            storage.input_hash(outreach.build_input({**stale_client, "reviews": 10}, profile)),
            "mimo-v2.5-pro",
            {**GOOD_ANSWER, "manual_observation": "", "review_evidence": []},
        )

        with (
            patch.object(main, "list_clients", return_value=[CLIENT, stale_client, missing_client]),
            patch.object(main, "client_stats", return_value={"total": 3}),
        ):
            response = main.clients()

        statuses = {item["id"]: item["ai_message_status"] for item in response["clients"]}
        self.assertEqual({28: "ready", 29: "stale", 30: "missing"}, statuses)
        self.assertTrue(response["clients"][0]["ai_message_created_at"])
        self.assertEqual("", response["clients"][2]["ai_message_created_at"])

    def test_cached_api_reopens_result_generated_with_observation_and_reviews(self) -> None:
        payload = {
            **REVIEW_ANSWER,
            "manual_observation": "В карточке нет ссылки на сайт",
            "review_evidence": REVIEW_EVIDENCE,
            "warnings": [],
        }
        storage.save_result(
            "client_message",
            "client",
            CLIENT["id"],
            storage.input_hash(
                outreach.build_input(
                    CLIENT,
                    get_profile(),
                    payload["manual_observation"],
                    REVIEW_EVIDENCE,
                )
            ),
            "mimo-v2.5-pro",
            payload,
        )

        with patch.object(main, "list_clients", return_value=[CLIENT]):
            response = main.ai_client_message_cached(CLIENT["id"])

        self.assertTrue(response["ready"])
        self.assertEqual("ready", response["status"])
        self.assertEqual("В карточке нет ссылки на сайт", response["manual_observation"])
        self.assertEqual(REVIEW_EVIDENCE, response["review_evidence"])
        self.assertEqual("https://semyon-lobanov-portfolio.vercel.app/", response["portfolio_url"])

    def test_whatsapp_link_carries_the_message_text(self) -> None:
        transport = RecordingTransport()

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        # WhatsApp должен быть первым: только он подставляет текст в диалог.
        self.assertEqual("WhatsApp", result["links"][0]["channel"])
        whatsapp = result["links"][0]
        self.assertTrue(whatsapp["url"].startswith("https://wa.me/79636775777?text="))
        self.assertIn(quote("Пациенты уточняют")[:20], whatsapp["url"])

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
        self.assertNotIn("от 90 000 ₽", transport.last_user_prompt)

    def test_link_in_first_contact_triggers_one_repair(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[0] = {
            **variants[0],
            "text": (
                "Здравствуйте! Посмотрел карточку 7R: https://example.com/promo. "
                "Где пациенты сейчас смотрят цены?"
            ),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))
        self.assertNotIn("https://", result["variants"][0]["text"])

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

    def test_spam_phrases_trigger_one_repair(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[0] = {
            **variants[0],
            "title": "Шаблон",
            "text": (
                "Здравствуйте! Меня зовут Семён, у меня уникальное предложение для 7R. "
                "Как сейчас пациенты записываются на приём?"
            ),
        }
        spammy = {
            **GOOD_ANSWER,
            "variants": variants,
        }
        transport = RecordingTransport(spammy, GOOD_ANSWER)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual([], result["warnings"])
        self.assertEqual(2, len(transport.calls))
        self.assertIn("меня зовут", transport.last_user_prompt.casefold())

    def test_too_short_variant_triggers_one_repair(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[0] = {**variants[0], "text": "Привет?"}
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(3, len(result["variants"]))
        self.assertEqual(2, len(transport.calls))
        self.assertIn("слишком короткий", transport.last_user_prompt)

    def test_too_long_variant_triggers_one_repair(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {
            **variants[1],
            "text": (
                variants[1]["text"].rstrip("?")
                + " "
                + ("Дополнительный неподтверждённый контекст. " * 12)
                + "Как сейчас устроена запись?"
            ),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(3, len(result["variants"]))
        self.assertEqual(2, len(transport.calls))
        self.assertIn("слишком длинный", transport.last_user_prompt)

    def test_commercial_pitch_in_first_contact_triggers_one_repair(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[0] = {
            **variants[0],
            "text": "Здравствуйте! Предлагаю сделать сайт за 35 000 ₽. Обсудим?",
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))
        self.assertEqual("Цены и информация", result["variants"][0]["title"])
        self.assertIn("коммерческое предложение", transport.last_user_prompt.casefold())

    def test_two_questions_in_first_contact_trigger_one_repair(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {
            **variants[1],
            "text": "Здравствуйте! Как сейчас записываются пациенты? Есть отдельная система?",
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))
        self.assertIn("ровно один вопрос", transport.last_user_prompt.casefold())

    def test_sender_name_is_not_used_as_the_client_salutation(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[2] = {
            **variants[2],
            "text": (
                "Семён, здравствуйте! У 7R рейтинг 5,0 и 200 отзывов. Кто отвечает "
                "пациентам, если они пишут вечером или администратор занят?"
            ),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants})

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertFalse(result["variants"][2]["text"].startswith("Семён,"))
        self.assertTrue(result["variants"][2]["text"].startswith("Здравствуйте!"))

    def test_weak_sales_question_triggers_one_repair(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {
            **variants[1],
            "text": (
                "Здравствуйте! В карточке 2GIS не вижу онлайн-записи для пациентов. "
                "Сайт сейчас актуален?"
            ),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))
        self.assertIn("актуален?", transport.last_user_prompt.casefold())

    def test_duplicate_or_missing_tones_are_repaired(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {**variants[1], "tone": "confident"}
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(["confident", "hard_sell", "expert"], [item["tone"] for item in result["variants"]])
        self.assertEqual(2, len(transport.calls))
        self.assertIn("ровно три стратегии", transport.last_user_prompt)

    def test_variant_titles_are_normalized_to_diagnostic_angles(self) -> None:
        variants = [
            {**item, "title": f"Произвольный заголовок {index}"}
            for index, item in enumerate(GOOD_ANSWER["variants"], start=1)
        ]

        result = outreach.generate_client_message(
            CLIENT,
            ai_client=client_for(RecordingTransport({**GOOD_ANSWER, "variants": variants})),
        )

        self.assertEqual(
            ["Цены и информация", "Запись и заявки", "Обработка обращений"],
            [item["title"] for item in result["variants"]],
        )

    def test_duplicate_questions_trigger_one_repair(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {**variants[1], "text": variants[0]["text"]}
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))
        self.assertIn("разными вопросами", transport.last_user_prompt)

    def test_variant_without_question_is_repaired(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[2] = {
            **variants[2],
            "text": GOOD_ANSWER["variants"][2]["text"].replace("?", "."),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))
        self.assertIn("ровно один вопрос", transport.last_user_prompt)

    def test_legacy_angle_variants_are_mapped_by_position(self) -> None:
        legacy = {
            **GOOD_ANSWER,
            "analysis": "Сильная карточка, но путь до обращения можно сделать понятнее.",
            "pain": "Следующий шаг после карточки неочевиден.",
            "money_argument": "Даже одно дополнительное обращение может окупить улучшение.",
            "variants": [
                {"angle": item["title"], "text": item["text"]}
                for item in GOOD_ANSWER["variants"]
            ],
        }
        transport = RecordingTransport(legacy)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(["confident", "hard_sell", "expert"], [item["tone"] for item in result["variants"]])

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
