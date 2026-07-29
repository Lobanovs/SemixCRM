from __future__ import annotations

import logging
import re
from typing import Any, Callable
from urllib.parse import quote

from .client import AiClient, AiDisabledError, AiError
from .profile import ExecutorProfile, get_profile
from .prompts import (
    MESSAGE_MAX_LENGTH,
    MESSAGE_MIN_LENGTH,
    SYSTEM_PROMPT,
    TONE_LENGTHS,
    build_client_message_prompt,
)
from .reviews import fetch_2gis_review_evidence
from .storage import get_cached, input_hash, save_result


logger = logging.getLogger(__name__)

TASK = "client_message"
ENTITY = "client"
PROMPT_VERSION = 8

MIN_LENGTH = MESSAGE_MIN_LENGTH
MAX_LENGTH = MESSAGE_MAX_LENGTH
TONE_ORDER = ("confident", "hard_sell", "expert")
TONE_TITLES = {
    "confident": "Цены и информация",
    "hard_sell": "Запись и заявки",
    "expert": "Обработка обращений",
}

# Фразы, по которым сообщение сразу читается как рассылка.
BANNED_PHRASES = (
    "меня зовут",
    "надеюсь, у вас всё хорошо",
    "надеюсь, у вас все хорошо",
    "уникальное предложение",
    "команда профессионалов",
    "индивидуальный подход",
    "под ключ",
    "в топ яндекса",
    "продающий сайт",
    "актуально?",
    "актуален?",
    "актуальна?",
    "актуальны?",
    "интересно?",
    "хотите?",
)

MARKDOWN = re.compile(r"[*_`#]{1,}")
# Адрес заканчивается буквой, цифрой или слэшем: жадное \S+ съедало закрывающую
# скобку и точку, и от «нет (http://site).» оставалось «нет (».
LINK = re.compile(r"https?://[\w\-./?%&=+#:@~]*[\w\-/#@~]")
EMPTY_BRACKETS = re.compile(r"[(\[]\s*[)\]]")
SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?)\]])")
CLAIMS_REVIEW_READING = re.compile(
    r"\b(?:почитал|прочитал|посмотрел|изучил)\w*\s+отзыв|\bклиенты\s+(?:часто\s+|особенно\s+)?отмеч",
    re.IGNORECASE,
)
COMMERCIAL_FIRST_CONTACT = re.compile(
    r"https?://|www\.|портфолио|(?:\d[\d\s]*)?\s*(?:₽|руб(?:\.|ля|лей|ль)?)|"
    r"\b(?:демо|прототип|презентаци\w*|созвон\w*|сотрудничеств\w*)\b|"
    r"\bпредлагаю\s+(?:сотрудничество|сделать|разработать)|"
    r"\b(?:сделаю|разработаю|соберу)\s+(?:для\s+вас\s+)?сайт|"
    r"\bя\s+(?:делаю|разрабатываю|создаю)\s+сайт|"
    r"\bмогу\s+(?:сделать|разработать|собрать|показать|прислать)|"
    r"\bпришлю\s+(?:варианты|стоимость|сроки|презентацию)|"
    r"\bответ(?:ьте|ить)\s+[«\"']?да[»\"']?",
    re.IGNORECASE,
)
SOURCE_DISCLOSURE = re.compile(
    r"\b2\s*(?:gis|гис)\b|\bдвухгис\w*\b|"
    r"\b(?:яндекс(?:\.?\s*карт\w*)?|yandex(?:\s+maps?)?|google\s+maps?)\b|"
    r"\b(?:карточк|отзыв|площадк|профил)\w*\b|"
    r"\b(?:наш[её]л|увидел|заметил|посмотрел|изучил|наткнулся)\b.{0,48}"
    r"\b(?:вас|ваш\w*|компани\w*|бизнес\w*)\b",
    re.IGNORECASE | re.DOTALL,
)


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    text = MARKDOWN.sub("", text)
    # Ссылки в первом сообщении режут доставляемость — убираем, даже если модель вставила.
    text = LINK.sub("", text)
    text = EMPTY_BRACKETS.sub("", text)
    text = SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _remove_sender_salutation(text: str, sender_name: str) -> str:
    name = sender_name.strip()
    if not name:
        return text
    cleaned = re.sub(rf"^{re.escape(name)}\s*[,!]\s*", "", text, count=1, flags=re.IGNORECASE)
    if cleaned == text or not cleaned:
        return text
    return cleaned[:1].upper() + cleaned[1:]


def _validate(
    payload: dict[str, Any],
    sender_name: str = "",
    review_evidence: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Приводит ответ модели к ожидаемой форме и собирает замечания."""

    warnings: list[str] = []
    evidence = review_evidence or []
    allowed_evidence_ids = {
        str(item.get("id") or "").strip()
        for item in evidence
        if str(item.get("id") or "").strip()
    }
    raw_review_insight = payload.get("review_insight") or {}
    if not isinstance(raw_review_insight, dict):
        raise AiError("review_insight должен быть JSON-объектом")
    review_summary = _clean_text(raw_review_insight.get("summary"))
    raw_evidence_ids = raw_review_insight.get("evidence_ids") or []
    if not isinstance(raw_evidence_ids, list):
        raise AiError("review_insight.evidence_ids должен быть массивом")
    evidence_ids = [str(item).strip() for item in raw_evidence_ids if str(item).strip()]
    unsupported_ids = [item for item in evidence_ids if item not in allowed_evidence_ids]
    if unsupported_ids:
        raise AiError(
            "review_insight содержит неизвестные evidence_ids: "
            + ", ".join(unsupported_ids)
        )
    if evidence and (not review_summary or not evidence_ids):
        raise AiError("При доступных отзывах review_insight должен содержать summary и evidence_ids")
    if not evidence and (review_summary or evidence_ids):
        raise AiError("Нельзя описывать отзывы без переданных доказательств 2GIS")

    variants: list[dict[str, str]] = []
    raw_variants = payload.get("variants") or []
    if not isinstance(raw_variants, list) or len(raw_variants) != len(TONE_ORDER):
        raise AiError(
            "Модель должна вернуть ровно три стратегии: confident, hard_sell и expert"
        )

    legacy = all(isinstance(item, dict) and not item.get("tone") for item in raw_variants)
    seen_tones: set[str] = set()
    seen_questions: set[str] = set()
    for index, item in enumerate(raw_variants):
        if not isinstance(item, dict):
            raise AiError("Каждый вариант сообщения должен быть JSON-объектом")
        tone = TONE_ORDER[index] if legacy else str(item.get("tone") or "").strip().casefold()
        if tone not in TONE_ORDER or tone in seen_tones:
            raise AiError(
                "Модель должна вернуть ровно три стратегии: confident, hard_sell и expert"
            )
        seen_tones.add(tone)
        raw_text = str(item.get("text") or "").strip()
        if SOURCE_DISCLOSURE.search(raw_text):
            raise AiError(
                f"Вариант «{TONE_TITLES[tone]}» раскрывает источник лида: "
                "не упоминай 2GIS, карточку, отзывы или способ поиска компании"
            )
        if COMMERCIAL_FIRST_CONTACT.search(raw_text):
            raise AiError(
                f"Вариант «{TONE_TITLES[tone]}» содержит коммерческое предложение, "
                "ссылку, цену или преждевременный следующий шаг"
            )
        text = _clean_text(raw_text)
        text = _remove_sender_salutation(text, sender_name)
        minimum, maximum = TONE_LENGTHS[tone]
        if len(text) < minimum:
            raise AiError(
                f"Вариант «{TONE_TITLES[tone]}» слишком короткий: "
                f"{len(text)} символов вместо {minimum}–{maximum}"
            )
        if len(text) > maximum:
            raise AiError(
                f"Вариант «{TONE_TITLES[tone]}» слишком длинный: "
                f"{len(text)} символов вместо {minimum}–{maximum}"
            )
        if text.count("?") != 1 or not text.endswith("?"):
            raise AiError(
                f"Вариант «{TONE_TITLES[tone]}» должен содержать ровно один вопрос "
                "и заканчиваться им"
            )
        if not evidence and CLAIMS_REVIEW_READING.search(text):
            raise AiError("Нельзя утверждать, что отзывы прочитаны, когда доказательства 2GIS недоступны")
        lowered = text.casefold()
        hits = [phrase for phrase in BANNED_PHRASES if phrase in lowered]
        if hits:
            raise AiError(f"В варианте остались шаблонные фразы: {', '.join(hits)}")
        normalized_question = re.sub(r"\s+", " ", text).casefold()
        if normalized_question in seen_questions:
            raise AiError("Модель должна вернуть три варианта с разными вопросами")
        seen_questions.add(normalized_question)
        title = TONE_TITLES[tone]
        variants.append({
            "tone": tone,
            "title": title,
            # Старое поле остаётся для совместимости с сохранёнными результатами.
            "angle": title,
            "text": text,
        })

    if tuple(item["tone"] for item in variants) != TONE_ORDER:
        raise AiError("Стратегии должны идти в порядке confident, hard_sell, expert")

    raw_analysis = payload.get("analysis")
    if isinstance(raw_analysis, dict):
        signal = _clean_text(raw_analysis.get("signal"))
        problem = _clean_text(raw_analysis.get("problem"))
        opportunity = _clean_text(raw_analysis.get("opportunity"))
        analysis = " ".join(part for part in (signal, problem, opportunity) if part)
    else:
        analysis = _clean_text(raw_analysis)
        signal = analysis
        problem = _clean_text(payload.get("pain"))
        opportunity = _clean_text(payload.get("money_argument"))

    result = {
        "analysis": analysis,
        "pain": _clean_text(payload.get("pain")) or problem,
        "money_argument": _clean_text(payload.get("money_argument")) or opportunity,
        "insights": {
            "signal": signal,
            "problem": problem,
            "opportunity": opportunity,
        },
        "review_insight": {
            "summary": review_summary,
            "evidence_ids": evidence_ids,
        },
        "variants": variants,
        "follow_up": _clean_text(payload.get("follow_up")),
    }
    return result, warnings


def _channel_links(client: dict[str, Any], text: str) -> list[dict[str, str]]:
    """Готовые ссылки с подставленным текстом — чтобы отправить в один клик."""

    encoded = quote(text)
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    # WhatsApp вперёд: только он умеет открыть диалог с уже подставленным текстом.
    contacts = sorted(
        client.get("contacts") or [],
        key=lambda item: 0 if str(item.get("type")) == "whatsapp" else 1,
    )
    for contact in contacts:
        kind = str(contact.get("type") or "")
        url = str(contact.get("url") or contact.get("value") or "").strip()
        if not url or kind in seen:
            continue
        if kind == "whatsapp" and "wa.me" in url:
            links.append({"channel": "WhatsApp", "url": f"{url.split('?')[0]}?text={encoded}"})
            seen.add(kind)
        elif kind == "telegram" and "t.me" in url:
            # Telegram не поддерживает предзаполнение в личной переписке — открываем диалог.
            links.append({"channel": "Telegram", "url": url.split("?")[0]})
            seen.add(kind)
    return links


def build_input(
    client: dict[str, Any],
    profile: ExecutorProfile,
    manual_observation: str = "",
    review_evidence: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Только те поля, изменение которых должно сбрасывать кэш."""

    return {
        "prompt_version": PROMPT_VERSION,
        "client": {
            key: client.get(key)
            for key in ("name", "city", "niche", "address", "phone", "website", "rating",
                        "reviews", "branch_count", "pain", "lead_score", "match_score",
                        "lead_score_reasons", "card_url")
        },
        "profile": profile.as_dict(),
        "manual_observation": manual_observation.strip(),
        "review_evidence": review_evidence or [],
    }


def generate_client_message(
    client: dict[str, Any],
    force: bool = False,
    manual_observation: str = "",
    ai_client: AiClient | None = None,
    review_loader: Callable[[str], list[dict[str, str]]] = fetch_2gis_review_evidence,
) -> dict[str, Any]:
    """Разбирает клиента и пишет варианты первого сообщения.

    Повторный вызов с теми же данными отдаёт сохранённый результат: генерация
    стоит денег и секунд, а карточка между открытиями обычно не меняется.
    """

    profile = get_profile()
    observation = manual_observation.strip()[:500]
    card_url = str(client.get("card_url") or "").strip()
    try:
        review_evidence = review_loader(card_url) if card_url else []
    except Exception as error:  # внешний источник не должен блокировать генерацию
        logger.info("Отзывы 2GIS не загрузились для клиента %s: %s", client.get("id"), error)
        review_evidence = []
    payload_input = build_input(client, profile, observation, review_evidence)
    fingerprint = input_hash(payload_input)
    client_id = int(client["id"])

    if not force:
        cached = get_cached(TASK, ENTITY, client_id, fingerprint)
        if cached is not None:
            first = cached["variants"][0]["text"] if cached.get("variants") else ""
            return {
                **cached,
                "portfolio_url": profile.portfolio_url,
                "links": _channel_links(client, first),
            }

    engine = ai_client or AiClient()
    if not engine.enabled:
        raise AiDisabledError("Не задан OPENCODE_API_KEY")

    raw = engine.complete_json(
        SYSTEM_PROMPT,
        build_client_message_prompt(client, profile, observation, review_evidence),
        # Ниже единицы: нужен предсказуемый деловой текст, а не творческий разброс.
        temperature=0.45,
        max_tokens=3600,
        validate=lambda payload: _validate(payload, profile.name, review_evidence),
    )
    result, warnings = _validate(raw, profile.name, review_evidence)
    if card_url and not review_evidence:
        warnings.append(
            "Отзывы 2GIS временно недоступны — текст подготовлен только по данным карточки."
        )
    result["warnings"] = warnings
    result["review_evidence"] = review_evidence
    result["manual_observation"] = observation
    save_result(TASK, ENTITY, client_id, fingerprint, engine.settings.model, result)

    first = result["variants"][0]["text"]
    return {
        **result,
        "cached": False,
        "model": engine.settings.model,
        "portfolio_url": profile.portfolio_url,
        "links": _channel_links(client, first),
    }
