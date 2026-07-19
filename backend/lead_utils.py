from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


LEAD_SCORE_MAX = 23
DIRECT_CONTACT_TYPES = {"telegram", "whatsapp", "email"}
SOCIAL_TYPES = {
    "telegram",
    "whatsapp",
    "vkontakte",
    "instagram",
    "facebook",
    "youtube",
    "twitter",
    "linkedin",
    "pinterest",
    "viber",
}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_business_text(value: Any) -> str:
    return re.sub(r"[^a-zа-я0-9]+", "", clean(value).lower().replace("ё", "е"))


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", clean(value))
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    return digits


def normalize_domain(value: Any) -> str:
    raw = clean(value)
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return parsed.netloc.lower().removeprefix("www.")


def is_real_website(value: Any) -> bool:
    domain = normalize_domain(value)
    if not domain:
        return False
    return not any(token in domain for token in ("t.me", "telegram.", "wa.me", "whatsapp.", "vk.com", "instagram.", "facebook.", "youtube.", "linkedin."))


def canonical_source_id(card_url: Any) -> str:
    value = clean(card_url).lower()
    if not value:
        return ""
    match = re.search(r"2gis\.(?:ru|com)/[^/]+/firm/(\d+)", value)
    if not match:
        match = re.search(r"2gis\.(?:ru|com)/firm/(\d+)", value)
    if match:
        return f"2gis:{match.group(1)}"
    match = re.search(r"yandex\.(?:ru|com)/maps/org/(?:[^/]+/)?(\d+)", value)
    if match:
        return f"yandex:{match.group(1)}"
    return ""


def business_identity_key(lead: dict[str, Any]) -> str:
    source_id = canonical_source_id(lead.get("card_url"))
    if source_id:
        return source_id

    name = normalize_business_text(lead.get("name"))
    city = normalize_business_text(lead.get("city"))
    address = normalize_business_text(lead.get("address"))
    if name and city and address:
        return f"business:{name}:{city}:{address}"
    if name and city:
        return f"business:{name}:{city}"

    phone = normalize_phone(lead.get("phone"))
    if phone:
        return f"phone:{phone}"
    domain = normalize_domain(lead.get("website"))
    if domain:
        return f"domain:{domain}"
    return f"fallback:{name}:{normalize_business_text(lead.get('source'))}"


def normalize_contact_type(contact_type: Any, value: Any = "") -> str:
    normalized = clean(contact_type).lower().replace("e-mail", "email")
    lowered_value = clean(value).lower()
    if normalized == "website":
        if "t.me/" in lowered_value or "telegram." in lowered_value:
            return "telegram"
        if "wa.me/" in lowered_value or "whatsapp." in lowered_value:
            return "whatsapp"
        if "vk.com/" in lowered_value:
            return "vkontakte"
    if normalized in {"phone", "email", "website", *SOCIAL_TYPES}:
        return normalized
    if "t.me/" in lowered_value or "telegram." in lowered_value:
        return "telegram"
    if "wa.me/" in lowered_value or "whatsapp." in lowered_value:
        return "whatsapp"
    if "vk.com/" in lowered_value:
        return "vkontakte"
    if "@" in lowered_value and "/" not in lowered_value:
        return "email"
    return normalized or "other"


def contacts_from_lead(lead: dict[str, Any]) -> list[dict[str, str]]:
    raw_contacts = lead.get("contacts")
    candidates: list[dict[str, Any]] = list(raw_contacts) if isinstance(raw_contacts, list) else []
    for contact_type, field in (("phone", "phone"), ("website", "website"), ("other", "social_url")):
        value = clean(lead.get(field))
        if value:
            candidates.append({"type": contact_type, "value": value, "url": value})

    labels = {
        "phone": "Телефон",
        "email": "E-mail",
        "website": "Сайт",
        "telegram": "Telegram",
        "whatsapp": "WhatsApp",
        "vkontakte": "ВКонтакте",
        "instagram": "Instagram",
        "facebook": "Facebook",
        "youtube": "YouTube",
        "viber": "Viber",
        "linkedin": "LinkedIn",
    }
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        value = clean(candidate.get("value") or candidate.get("text") or candidate.get("url"))
        url = clean(candidate.get("url") or value)
        contact_type = normalize_contact_type(candidate.get("type"), url or value)
        if not value:
            continue
        identity_value = normalize_phone(value) if contact_type == "phone" else value.lower().split("?text=", 1)[0]
        identity = (contact_type, identity_value)
        if identity in seen:
            continue
        seen.add(identity)
        if contact_type == "whatsapp":
            url = url.split("?text=", 1)[0]
        result.append({
            "type": contact_type,
            "label": clean(candidate.get("label")) or labels.get(contact_type, "Контакт"),
            "value": value,
            "url": url,
        })
    return result


def direct_contact_types(lead: dict[str, Any]) -> list[str]:
    return sorted({contact["type"] for contact in contacts_from_lead(lead) if contact["type"] in DIRECT_CONTACT_TYPES})


def is_high_ticket_niche(niche: Any) -> bool:
    normalized = clean(niche).lower()
    needles = (
        "стомат", "клиник", "мед", "юрист", "адвокат", "автосервис",
        "детейлинг", "ремонт авто", "турфир", "туризм", "недвиж",
        "строител", "ремонт квартир", "фитнес",
    )
    return any(needle in normalized for needle in needles)


def calculate_lead_score(lead: dict[str, Any]) -> tuple[int, list[str], int]:
    score = 0
    reasons: list[str] = []
    website = clean(lead.get("website"))
    has_real_website = is_real_website(website)
    phone = clean(lead.get("phone"))
    rating = _float(lead.get("rating"))
    reviews = _int(lead.get("reviews")) or 0
    branches = _int(lead.get("branch_count")) or 0
    direct_channels = direct_contact_types(lead)

    if not has_real_website:
        score += 5
        reasons.append("Нет сайта +5")
    if phone:
        score += 2
        reasons.append("Есть телефон +2")
    if rating is not None and rating > 4.0:
        score += 2
        reasons.append("Рейтинг выше 4,0 +2")
    if reviews > 30:
        score += 3
        reasons.append("Больше 30 отзывов +3")
    if direct_channels and not has_real_website:
        score += 4
        channel_names = {"telegram": "Telegram", "whatsapp": "WhatsApp", "email": "e-mail"}
        reasons.append(f"Есть прямой контакт ({', '.join(channel_names[item] for item in direct_channels)}) +4")
    if branches > 1:
        score += 4
        reasons.append("Несколько филиалов +4")
    if is_high_ticket_niche(lead.get("niche")):
        score += 3
        reasons.append("Ниша с высоким чеком +3")

    match_score = round(score / LEAD_SCORE_MAX * 100) if score else 0
    return score, reasons, min(100, match_score)


def _float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ".")) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
