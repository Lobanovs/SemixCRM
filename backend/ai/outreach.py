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
PROMPT_VERSION = 6

MIN_LENGTH = MESSAGE_MIN_LENGTH
MAX_LENGTH = MESSAGE_MAX_LENGTH
TONE_ORDER = ("confident", "hard_sell", "expert")
TONE_TITLES = {
    "confident": "По отзывам и точке роста",
    "hard_sell": "Решение и портфолио",
    "expert": "Короткий контакт",
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
)

MARKDOWN = re.compile(r"[*_`#]{1,}")
# Адрес заканчивается буквой, цифрой или слэшем: жадное \S+ съедало закрывающую
# скобку и точку, и от «нет (http://site).» оставалось «нет (».
LINK = re.compile(r"https?://[\w\-./?%&=+#:@~]*[\w\-/#@~]")
EMPTY_BRACKETS = re.compile(r"[(\[]\s*[)\]]")
SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?)\]])")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
STANDALONE_GREETING = re.compile(r"^(?:здравствуйте|добрый день|добрый вечер|привет)[!.]?$", re.IGNORECASE)
WEAK_FINAL_QUESTION = re.compile(
    r"^(?:интересно|актуально|скинуть|посмотрите|посмотреть|"
    r"вам\s+(?:будет\s+)?удобно(?:\s+будет)?\s+посмотреть|"
    r"хотите\s+.+|готовы\s+.+|нужно\s+.+)\?$",
    re.IGNORECASE,
)
REPLY_CTA = re.compile(r"\bответ(?:ьте|ить)\s+[«\"']?да[»\"']?", re.IGNORECASE)
CLAIMS_REVIEW_READING = re.compile(
    r"\b(?:почитал|прочитал|посмотрел|изучил)\w*\s+отзыв|\bклиенты\s+(?:часто\s+|особенно\s+)?отмеч",
    re.IGNORECASE,
)
UNSUPPORTED_VOLUME_PERIOD = re.compile(
    r"\b\d+(?:\s*[–—-]\s*\d+)?\s+"
    r"(?:(?:нов\w*|дополнительн\w*|лишн\w*)\s+)?"
    r"(?:обращен\w*|заяв\w*|запис\w*|пациент\w*|клиент\w*)\s+"
    r"в\s+(?:день|недел\w*|месяц\w*|квартал\w*|год\w*)",
    re.IGNORECASE,
)
UNSUPPORTED_DEADLINE = re.compile(
    r"\bза\s+(?:\d+\s+)?(?:дн\w*|недел\w*|месяц\w*)",
    re.IGNORECASE,
)
DIRECT_SITE_ABSENCE = re.compile(r"\bбез\s+(?:полноценного\s+)?сайта\b", re.IGNORECASE)


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


def _truncate_at_word(text: str, limit: int, suffix: str = "…") -> str:
    if len(text) <= limit:
        return text
    if limit <= len(suffix):
        return suffix[:limit]
    head = text[:limit - len(suffix)].rstrip()
    if " " in head:
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,;:—-") + suffix


def _remove_sender_salutation(text: str, sender_name: str) -> str:
    name = sender_name.strip()
    if not name:
        return text
    cleaned = re.sub(rf"^{re.escape(name)}\s*[,!]\s*", "", text, count=1, flags=re.IGNORECASE)
    if cleaned == text or not cleaned:
        return text
    return cleaned[:1].upper() + cleaned[1:]


def _strengthen_final_question(text: str) -> str:
    sentences = [part.strip() for part in SENTENCE_BREAK.split(text) if part.strip()]
    if not sentences or not WEAK_FINAL_QUESTION.fullmatch(sentences[-1]):
        return text
    sentences[-1] = "Куда удобнее прислать короткий разбор?"
    return " ".join(sentences)


def _drop_unsupported_claims(text: str) -> str:
    grounded_paragraphs: list[str] = []
    for paragraph in re.split(r"\n{2,}", text):
        sentences = [part.strip() for part in SENTENCE_BREAK.split(paragraph) if part.strip()]
        grounded: list[str] = []
        for part in sentences:
            lowered = part.casefold()
            if "конкурент" in lowered or DIRECT_SITE_ABSENCE.search(part):
                continue
            if UNSUPPORTED_VOLUME_PERIOD.search(part):
                continue
            grounded.append(UNSUPPORTED_DEADLINE.sub("в первую очередь", part))
        if grounded:
            grounded_paragraphs.append(" ".join(grounded))
    return "\n\n".join(grounded_paragraphs) if grounded_paragraphs else text


def _compact_message(text: str, max_length: int = MAX_LENGTH) -> str:
    """Сжимает редкий длинный ответ модели, сохраняя оффер и финальный вопрос."""

    if len(text) <= max_length:
        return text

    sentences = [part.strip() for part in SENTENCE_BREAK.split(text) if part.strip()]
    if len(sentences) > 1 and STANDALONE_GREETING.fullmatch(sentences[0]):
        sentences = sentences[1:]
    compact = " ".join(sentences)
    if len(compact) <= max_length:
        return compact

    question_index = next(
        (index for index in range(len(sentences) - 1, -1, -1) if "?" in sentences[index]),
        len(sentences) - 1,
    )
    # Обычно предпоследнее предложение содержит конкретный следующий шаг,
    # а последнее — лёгкий вопрос. Их нельзя потерять при сокращении.
    tail_start = max(0, question_index - 1)
    tail = sentences[tail_start:question_index + 1]
    tail_text = " ".join(tail)
    if len(tail_text) > max_length:
        question = sentences[question_index]
        if len(question) >= max_length:
            return _truncate_at_word(question.rstrip("?"), max_length - 1, "") + "?"
        offer_limit = max_length - len(question) - 1
        offer = _truncate_at_word(sentences[tail_start], offer_limit)
        return f"{offer} {question}".strip()

    selected: list[str] = []
    context = sentences[:tail_start]
    for sentence in context:
        candidate = " ".join([*selected, sentence, *tail])
        if len(candidate) <= max_length:
            selected.append(sentence)

    result = " ".join([*selected, *tail]).strip()
    return result if len(result) <= max_length else result[:max_length].rstrip()


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
    for index, item in enumerate(raw_variants):
        if not isinstance(item, dict):
            raise AiError("Каждый вариант сообщения должен быть JSON-объектом")
        tone = TONE_ORDER[index] if legacy else str(item.get("tone") or "").strip().casefold()
        if tone not in TONE_ORDER or tone in seen_tones:
            raise AiError(
                "Модель должна вернуть ровно три стратегии: confident, hard_sell и expert"
            )
        seen_tones.add(tone)
        text = _clean_text(item.get("text"))
        text = _remove_sender_salutation(text, sender_name)
        text = _strengthen_final_question(text)
        text = _drop_unsupported_claims(text)
        minimum, maximum = TONE_LENGTHS[tone]
        text = _compact_message(text, maximum)
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
        if "?" not in text and REPLY_CTA.search(text) is None:
            raise AiError(
                f"В варианте «{TONE_TITLES[tone]}» нет вопроса или CTA с ответом «да»"
            )
        if not evidence and CLAIMS_REVIEW_READING.search(text):
            raise AiError("Нельзя утверждать, что отзывы прочитаны, когда доказательства 2GIS недоступны")
        if evidence and tone == "confident" and "отзыв" not in text.casefold():
            raise AiError("Основной вариант должен использовать подтверждённую деталь из отзывов")
        lowered = text.casefold()
        hits = [phrase for phrase in BANNED_PHRASES if phrase in lowered]
        if hits:
            raise AiError(f"В варианте остались шаблонные фразы: {', '.join(hits)}")
        title = _clean_text(item.get("title") or item.get("angle")) or TONE_TITLES[tone]
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
