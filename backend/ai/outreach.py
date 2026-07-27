from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

from .client import AiClient, AiDisabledError, AiError
from .profile import ExecutorProfile, get_profile
from .prompts import SYSTEM_PROMPT, build_client_message_prompt
from .storage import get_cached, input_hash, save_result


logger = logging.getLogger(__name__)

TASK = "client_message"
ENTITY = "client"

MIN_LENGTH = 120
MAX_LENGTH = 900

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


def _validate(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Приводит ответ модели к ожидаемой форме и собирает замечания."""

    warnings: list[str] = []
    variants: list[dict[str, str]] = []
    for item in payload.get("variants") or []:
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("text"))
        if len(text) < MIN_LENGTH:
            warnings.append(f"Вариант «{str(item.get('angle'))[:24]}» слишком короткий, пропущен")
            continue
        if len(text) > MAX_LENGTH:
            text = text[:MAX_LENGTH].rsplit(" ", 1)[0] + "…"
            warnings.append("Один вариант пришлось обрезать по длине")
        lowered = text.casefold()
        hits = [phrase for phrase in BANNED_PHRASES if phrase in lowered]
        if hits:
            warnings.append(f"В варианте остались шаблонные фразы: {', '.join(hits)}")
        variants.append({"angle": _clean_text(item.get("angle")) or "Вариант", "text": text})

    result = {
        "analysis": _clean_text(payload.get("analysis")),
        "pain": _clean_text(payload.get("pain")),
        "money_argument": _clean_text(payload.get("money_argument")),
        "variants": variants,
        "follow_up": _clean_text(payload.get("follow_up")),
    }
    if not variants:
        raise AiError("Модель не вернула ни одного пригодного варианта сообщения")
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


def build_input(client: dict[str, Any], profile: ExecutorProfile) -> dict[str, Any]:
    """Только те поля, изменение которых должно сбрасывать кэш."""

    return {
        "client": {
            key: client.get(key)
            for key in ("name", "city", "niche", "address", "phone", "website", "rating",
                        "reviews", "branch_count", "pain", "lead_score", "match_score",
                        "lead_score_reasons")
        },
        "profile": profile.as_dict(),
    }


def generate_client_message(
    client: dict[str, Any],
    force: bool = False,
    ai_client: AiClient | None = None,
) -> dict[str, Any]:
    """Разбирает клиента и пишет варианты первого сообщения.

    Повторный вызов с теми же данными отдаёт сохранённый результат: генерация
    стоит денег и секунд, а карточка между открытиями обычно не меняется.
    """

    profile = get_profile()
    payload_input = build_input(client, profile)
    fingerprint = input_hash(payload_input)
    client_id = int(client["id"])

    if not force:
        cached = get_cached(TASK, ENTITY, client_id, fingerprint)
        if cached is not None:
            first = cached["variants"][0]["text"] if cached.get("variants") else ""
            return {**cached, "links": _channel_links(client, first)}

    engine = ai_client or AiClient()
    if not engine.enabled:
        raise AiDisabledError("Не задан OPENCODE_API_KEY")

    raw = engine.complete_json(
        SYSTEM_PROMPT,
        build_client_message_prompt(client, profile),
        # Ниже единицы: нужен предсказуемый деловой текст, а не творческий разброс.
        temperature=0.6,
        max_tokens=1800,
    )
    result, warnings = _validate(raw)
    result["warnings"] = warnings
    save_result(TASK, ENTITY, client_id, fingerprint, engine.settings.model, result)

    first = result["variants"][0]["text"]
    return {**result, "cached": False, "model": engine.settings.model, "links": _channel_links(client, first)}
