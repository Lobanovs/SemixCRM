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
        "problem": "В карточке не указан полноценный сайт, следующим шагом остаётся Telegram.",
        "opportunity": "Можно упростить путь от карточки до обращения и показать услуги клиники.",
    },
    "review_insight": {"summary": "", "evidence_ids": []},
    "variants": [
        {
            "tone": "confident",
            "title": "По отзывам и точке роста",
            "text": "Здравствуйте!\n\n"
                    "Посмотрел карточку «7R» в 2GIS. У вас рейтинг 5,0 и 200 отзывов — видно, "
                    "что клиника уже заслужила доверие пациентов.\n\n"
                    "При этом в карточке 2GIS не увидел отдельного сайта, где человек может "
                    "спокойно посмотреть услуги, врачей, цены и оставить заявку. Если пациент "
                    "выбирает клинику вечером или пока не готов звонить, он может закрыть карточку "
                    "и продолжить поиск.\n\n"
                    "Я разрабатываю сайты для бизнеса и могу сделать для «7R» понятный сайт с "
                    "услугами, ценами и онлайн-записью. Новые обращения будут сразу приходить "
                    "администратору в мессенджер или на почту.\n\n"
                    "Если сайт для вас сейчас актуален, просто ответьте «да» — пришлю варианты "
                    "по стоимости и срокам без созвона и длинной презентации.",
        },
        {
            "tone": "hard_sell",
            "title": "Решение и портфолио",
            "text": "Здравствуйте!\n\n"
                    "Нашёл «7R» в 2GIS: у клиники высокий рейтинг и 200 отзывов, но отдельной "
                    "ссылки на сайт в карточке не увидел. Пациенту приходится сразу переходить "
                    "в Telegram, не посмотрев в одном месте врачей, услуги и цены.\n\n"
                    "Я могу собрать понятный сайт клиники с онлайн-записью и передачей заявок "
                    "администратору. Он поможет превратить уже заработанное доверие в более простой "
                    "путь до обращения.\n\n"
                    "Если рассматриваете сайт, ответьте «да» — пришлю варианты по бюджету и срокам "
                    "без обязательного созвона.",
        },
        {
            "tone": "expert",
            "title": "Короткий контакт",
            "text": "Здравствуйте! Посмотрел карточку «7R» в 2GIS: рейтинг 5,0 и 200 отзывов уже "
                    "дают сильное доверие, но отдельного сайта с услугами и записью в карточке не "
                    "увидел. Я делаю такие сайты для бизнеса. Если вопрос актуален, ответьте «да» — "
                    "пришлю ориентиры по стоимости и срокам без созвона.",
        },
    ],
    "follow_up": "Здравствуйте! Возвращаюсь к вопросу сайта. Если он ещё актуален, пришлю варианты по стоимости и срокам.",
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
            "text": "Здравствуйте!\n\n"
                    "Посмотрел карточку «7R» в 2GIS и почитал отзывы. Обратил внимание, что клиенты "
                    "особенно отмечают косметолога Анну, спокойную атмосферу и внимательное "
                    "отношение. Видно, что у вас уже сложилась хорошая репутация и люди вам доверяют.\n\n"
                    "При этом в карточке 2GIS не увидел отдельного сайта, где можно спокойно "
                    "посмотреть все услуги, цены и оставить заявку. Если человек выбирает вечером "
                    "или пока не готов звонить, он может закрыть карточку и продолжить поиск.\n\n"
                    "Я разрабатываю сайты для бизнеса и могу сделать для «7R» понятный сайт с "
                    "услугами, ценами и онлайн-записью. Новые заявки будут сразу приходить "
                    "администратору в мессенджер или на почту.\n\n"
                    "Если сайт для вас сейчас актуален, просто ответьте «да» — пришлю варианты по "
                    "стоимости и срокам без созвона и длинной презентации.",
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

    def test_system_prompt_defines_three_tones_and_safe_missing_site_wording(self) -> None:
        for tone in ("confident", "hard_sell", "expert"):
            self.assertIn(tone, SYSTEM_PROMPT)
        for title in ("По отзывам и точке роста", "Решение и портфолио", "Короткий контакт"):
            self.assertIn(title, SYSTEM_PROMPT)
        self.assertIn("650–1100", SYSTEM_PROMPT)
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

    def test_generates_three_variants_with_analysis_and_follow_up(self) -> None:
        transport = RecordingTransport()

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(3, len(result["variants"]))
        self.assertEqual(
            ["confident", "hard_sell", "expert"],
            [item["tone"] for item in result["variants"]],
        )
        self.assertEqual("По отзывам и точке роста", result["variants"][0]["title"])
        self.assertTrue(result["analysis"])
        self.assertTrue(result["pain"])
        self.assertTrue(result["follow_up"])
        self.assertFalse(result["cached"])
        self.assertEqual([], result["review_evidence"])
        self.assertEqual("https://semyon-lobanov-portfolio.vercel.app/", result["portfolio_url"])
        self.assertEqual([], result["warnings"])

    def test_accepts_a_compact_second_variant_instead_of_losing_all_three_texts(self) -> None:
        compact_text = (
            "Здравствуйте!\n\n"
            "Посмотрел карточку «7R» в 2GIS. У клиники высокий рейтинг и много отзывов, но не увидел "
            "отдельного сайта с услугами, врачами, ценами и онлайн-записью. Человек, который выбирает "
            "вечером или не готов звонить, может продолжить поиск.\n\n"
            "Я делаю сайты с онлайн-записью и передачей заявок администратору в мессенджер или на почту. "
            "Если сайт сейчас актуален, ответьте «да» — пришлю варианты по стоимости и срокам без созвона."
        )
        self.assertGreaterEqual(len(compact_text), 350)
        self.assertLess(len(compact_text), 450)
        answer = {
            **GOOD_ANSWER,
            "variants": [
                GOOD_ANSWER["variants"][0],
                {**GOOD_ANSWER["variants"][1], "text": compact_text},
                GOOD_ANSWER["variants"][2],
            ],
        }

        result = outreach.generate_client_message(
            CLIENT,
            ai_client=client_for(RecordingTransport(answer)),
        )

        self.assertEqual(compact_text, result["variants"][1]["text"])

    def test_prompt_version_invalidates_legacy_cached_results(self) -> None:
        self.assertEqual(6, outreach.build_input(CLIENT, get_profile())["prompt_version"])

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
        self.assertIn("почитал отзывы", result["variants"][0]["text"])
        self.assertEqual([], result["warnings"])
        self.assertIn("[R1]", transport.last_user_prompt)

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
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[0] = {
            **variants[0],
            "title": "**По отзывам и точке роста**",
            "text": GOOD_ANSWER["variants"][0]["text"]
                    .replace("Посмотрел карточку", "**Посмотрел карточку**", 1)
                    .replace("в 2GIS.", "в 2GIS: https://example.com/promo.", 1),
        }
        dirty = {
            **GOOD_ANSWER,
            "variants": variants,
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

    def test_spam_phrases_trigger_one_repair(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[0] = {
            **variants[0],
            "title": "Шаблон",
            "text": "Здравствуйте! Меня зовут Семён, и у меня для «7R» уникальное предложение: "
                    "сайт под ключ от команды профессионалов с индивидуальным подходом.\n\n"
                    + GOOD_ANSWER["variants"][0]["text"],
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

    def test_too_long_variant_is_compacted_without_an_extra_model_call(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {
            **variants[1],
            "text": variants[1]["text"] + " " + ("Проверим гипотезу. " * 30),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(3, len(result["variants"]))
        self.assertEqual(1, len(transport.calls))
        self.assertLessEqual(
            len(result["variants"][1]["text"]),
            outreach.TONE_LENGTHS["hard_sell"][1],
        )
        self.assertIn("ответьте «да»", result["variants"][1]["text"])

    def test_repeated_overlong_answer_is_compacted_without_losing_the_next_step(self) -> None:
        variants = [
            {**item, "text": item["text"] + " " + ("Дополнительный контекст. " * 80)}
            for item in GOOD_ANSWER["variants"]
        ]
        overlong = {**GOOD_ANSWER, "variants": variants}
        transport = RecordingTransport(overlong, overlong)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertTrue(all(
            len(item["text"]) <= outreach.TONE_LENGTHS[item["tone"]][1]
            for item in result["variants"]
        ))
        self.assertTrue(all("ответьте «да»" in item["text"] for item in result["variants"]))

    def test_compaction_keeps_complete_sentences_instead_of_mid_sentence_ellipsis(self) -> None:
        text = (
            "У «7R» рейтинг 5,0 и 200 отзывов — доверие пациентов уже заработано. "
            "Потенциальному пациенту приходится самостоятельно собирать подробную информацию "
            "о врачах, услугах, стоимости, гарантиях и способах записи из нескольких источников. "
            "Могу прислать короткий разбор с тремя конкретными точками роста для карточки и сайта. "
            "Куда удобнее отправить материал?"
        )

        compacted = outreach._compact_message(text)

        self.assertLessEqual(len(compacted), outreach.MAX_LENGTH)
        self.assertGreaterEqual(len(compacted), outreach.MIN_LENGTH)
        self.assertNotIn("…", compacted)
        self.assertIn("Могу прислать короткий разбор", compacted)
        self.assertTrue(compacted.endswith("Куда удобнее отправить материал?"))

    def test_unsupported_competitor_claim_is_removed_without_an_extra_model_call(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {
            **variants[1],
            "text": GOOD_ANSWER["variants"][1]["text"].replace(
                "\n\nЯ могу собрать",
                "\n\nПока вы без сайта, конкуренты забирают пациентов из поиска.\n\nЯ могу собрать",
                1,
            ),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants})

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        text = result["variants"][1]["text"]
        self.assertNotIn("конкурент", text.casefold())
        self.assertGreaterEqual(len(text), outreach.MIN_LENGTH)
        self.assertEqual(1, len(transport.calls))

    def test_unsupported_volume_site_and_deadline_claims_are_removed(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {
            **variants[1],
            "text": GOOD_ANSWER["variants"][1]["text"].replace(
                "\n\nЯ могу собрать",
                "\n\nНо без сайта эта репутация работает только через сарафан. "
                "Даже 2–3 дополнительных обращения в месяц могут заметно увеличить выручку. "
                "Покажу, что можно исправить за неделю.\n\nЯ могу собрать",
                1,
            ),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants})

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        text = result["variants"][1]["text"]
        self.assertNotIn("2–3", text)
        self.assertNotIn("без сайта", text.casefold())
        self.assertNotIn("за неделю", text.casefold())
        self.assertIn("в первую очередь", text.casefold())
        self.assertGreaterEqual(len(text), outreach.MIN_LENGTH)
        self.assertLessEqual(len(text), outreach.MAX_LENGTH)
        self.assertEqual(1, len(transport.calls))

    def test_sender_name_is_not_used_as_the_client_salutation(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[2] = {
            **variants[2],
            "text": "Семён, добрый день. У «7R» рейтинг 5,0 и 200 отзывов — это сильная база доверия. "
                    "В карточке не вижу полноценного сайта, поэтому путь до записи стоит проверить. "
                    "Могу прислать короткий разбор с тремя точками роста. Куда удобнее отправить?",
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants})

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertFalse(result["variants"][2]["text"].startswith("Семён,"))
        self.assertTrue(result["variants"][2]["text"].startswith("Добрый день."))

    def test_weak_closed_question_is_replaced_with_a_specific_next_step(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {
            **variants[1],
            "text": GOOD_ANSWER["variants"][1]["text"].replace(
                "Если рассматриваете сайт, ответьте «да» — пришлю варианты по бюджету и срокам "
                "без обязательного созвона.",
                "Могу прислать подробные варианты по бюджету, срокам и составу работ без "
                "обязательного созвона. Интересно?",
            ),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants})

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        text = result["variants"][1]["text"]
        self.assertNotIn("Интересно?", text)
        self.assertTrue(text.endswith("Куда удобнее прислать короткий разбор?"))
        self.assertLessEqual(len(text), outreach.MAX_LENGTH)
        self.assertEqual(1, len(transport.calls))

    def test_duplicate_or_missing_tones_are_repaired(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[1] = {**variants[1], "tone": "confident"}
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        result = outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(["confident", "hard_sell", "expert"], [item["tone"] for item in result["variants"]])
        self.assertEqual(2, len(transport.calls))
        self.assertIn("ровно три стратегии", transport.last_user_prompt)

    def test_variant_without_question_is_repaired(self) -> None:
        variants = [dict(item) for item in GOOD_ANSWER["variants"]]
        variants[2] = {
            **variants[2],
            "text": GOOD_ANSWER["variants"][2]["text"].replace(
                "Если вопрос актуален, ответьте «да» — пришлю ориентиры по стоимости и срокам без созвона.",
                "Я подготовлю ориентиры по стоимости и срокам без обязательного созвона.",
            ),
        }
        transport = RecordingTransport({**GOOD_ANSWER, "variants": variants}, GOOD_ANSWER)

        outreach.generate_client_message(CLIENT, ai_client=client_for(transport))

        self.assertEqual(2, len(transport.calls))
        self.assertIn("вопроса или CTA", transport.last_user_prompt)

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
