from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from .lead_utils import business_identity_key
from .parser2gis_runtime import ensure_parser2gis_command, resolve_parser2gis_city_code


ROOT_DIR = Path(__file__).resolve().parents[1]
LEADHUNT_DIR = Path(os.getenv("LEADHUNT_ROOT", r"C:\Users\Admin\Desktop\LeadHunt"))
YANDEX_RUNNER = ROOT_DIR / "backend" / "yandex_runner.py"
OUTPUT_DIR = ROOT_DIR / "backend" / "data" / "parser_output"


def resolve_city_code(city: str, parser_python: str | None = None) -> str:
    clean_city = city.strip().lower()
    if not clean_city:
        raise ValueError("Укажите город для парсинга")
    if parser_python:
        upstream_code = resolve_parser2gis_city_code(parser_python, city)
        if upstream_code:
            return upstream_code
    aliases = {
        "москва": "moscow",
        "санкт-петербург": "spb",
        "санкт петербург": "spb",
        "питер": "spb",
        "новосибирск": "novosibirsk",
        "казань": "kazan",
        "самара": "samara",
        "краснодар": "krasnodar",
        "екатеринбург": "ekaterinburg",
        "нижний новгород": "n_novgorod",
        "уфа": "ufa",
        "ростов-на-дону": "rostov",
        "ростов на дону": "rostov",
    }
    return aliases.get(clean_city, clean_city.replace(" ", "_"))


def build_2gis_search_url(city_code: str, niche: str, start_page: int = 1) -> str:
    """Build the URL expected by parser-2gis for a selected start page."""
    page = max(1, int(start_page))
    page_segment = f"/page/{page}" if page > 1 else ""
    # Город экранируется так же, как ниша: иначе «/» или «?» в названии
    # уводят реальный Chrome на произвольный путь внутри 2gis.ru.
    safe_city = quote(city_code.strip("/"), safe="")
    if not safe_city:
        raise ValueError("Не удалось определить код города для 2GIS")
    return f"https://2gis.ru/{safe_city}/search/{quote(niche, safe='')}{page_segment}/filters/sort=name"


def _python_command() -> list[str]:
    configured = os.getenv("LEADHUNT_PYTHON", "").strip()
    if configured:
        return [configured]
    # The optional Yandex Maps bridge runs outside the isolated 2GIS runtime.
    launcher = shutil.which("py")
    if launcher:
        return [launcher, "-3"]
    return [sys.executable]


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    """Убивает parser-2gis вместе с Chrome, который он поднял отдельным деревом."""

    if process.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError):
            process.kill()
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _run_parser_process(cmd: list[str], environment: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    process = subprocess.Popen(
        cmd, cwd=str(ROOT_DIR), env=environment, text=True,
        encoding="utf-8", errors="replace", stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        creationflags=creation_flags, start_new_session=sys.platform != "win32",
    )
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        # Дочитываем то, что успел напечатать процесс, но не ждём вечно закрытия трубы.
        try:
            output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            output = ""
        raise
    return subprocess.CompletedProcess(cmd, process.returncode, output, "")


def collect_2gis(
    city: str,
    niche: str,
    limit: int,
    on_status: Callable[[str], None] | None = None,
    start_page: int = 1,
) -> list[dict[str, Any]]:
    parser_command = ensure_parser2gis_command(on_status)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"2gis_{uuid.uuid4().hex[:10]}.json"
    city_code = resolve_city_code(city, parser_command[0])
    url = build_2gis_search_url(city_code, niche, start_page)
    cmd = parser_command + [
        "-i", url, "-o", str(output_path), "-f", "json",
        # Real 2GIS checks currently send headless Chrome to CAPTCHA.
        "--chrome.headless", os.getenv("PARSER2GIS_HEADLESS", os.getenv("LEADHUNT_HEADLESS", "no")),
        "--chrome.start-maximized", "yes",
        "--chrome.silent-browser", "yes",
        "--parser.max-records", str(max(1, min(int(limit), 200))),
        "--writer.verbose", "yes",
    ]
    if on_status:
        page_label = f", страница {max(1, int(start_page))}" if int(start_page) > 1 else ""
        on_status(f"Открываю 2GIS: {city}, {niche}{page_label}")
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    timeout = max(180, min(600, 20 + int(limit) * 12))
    try:
        try:
            completed = _run_parser_process(cmd, environment, timeout)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Парсер 2GIS превысил лимит {timeout} секунд") from error
        output = completed.stdout or ""
        if on_status and output:
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            if lines:
                on_status(lines[-1][:180])
        if completed.returncode != 0:
            tail = "\n".join(output.splitlines()[-8:])
            raise RuntimeError(f"parser-2gis завершился с кодом {completed.returncode}: {tail}")
        if not output_path.exists() or output_path.stat().st_size <= 4:
            raise RuntimeError("parser-2gis завершился без результатов. Возможно, 2GIS показал CAPTCHA.")
        leads = load_2gis_json(output_path, city, niche, limit)
    finally:
        # Промежуточный дамп содержит телефоны и адреса и больше не нужен:
        # данные уже в SQLite, где работают архив и удаление.
        if os.getenv("PARSER2GIS_KEEP_OUTPUT", "").strip().lower() not in {"1", "yes", "true"}:
            output_path.unlink(missing_ok=True)
    if not leads:
        raise RuntimeError("parser-2gis не вернул карточки. Оставьте PARSER2GIS_HEADLESS=no и повторите запуск.")
    return leads


def collect_yandex(city: str, niche: str, limit: int, on_status: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    if not YANDEX_RUNNER.exists():
        raise FileNotFoundError(f"Не найден запускатель Яндекс Карт: {YANDEX_RUNNER}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"yandex_{uuid.uuid4().hex[:10]}.json"
    if on_status:
        on_status(f"Открываю Яндекс Карты: {city}, {niche}")
    command = _python_command() + [
        str(YANDEX_RUNNER), "--city", city, "--niche", niche,
        "--limit", str(max(1, min(limit, 50))), "--output", str(output_path),
    ]
    environment = os.environ.copy()
    environment.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "LEADHUNT_ROOT": str(LEADHUNT_DIR),
        "LEADHUNT_BROWSER_HEADLESS": os.getenv("LEADHUNT_BROWSER_HEADLESS", "true"),
    })
    timeout = max(180, min(600, 30 + int(limit) * 15))
    try:
        completed = subprocess.run(
            command, cwd=str(ROOT_DIR), env=environment, text=True, encoding="utf-8",
            errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Парсер Яндекс Карт превысил лимит {timeout} секунд") from error
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout or "").splitlines()[-10:])
        raise RuntimeError(f"Парсер Яндекс Карт завершился с кодом {completed.returncode}: {tail}")
    if not output_path.exists():
        raise RuntimeError("Парсер Яндекс Карт не создал файл результата")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    result: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict) or not _clean(item.get("name")):
            continue
        lead = {
            **item,
            "source": "Яндекс Карты",
            "city": item.get("city") or city,
            "niche": item.get("niche") or niche,
        }
        lead["contacts"] = _flat_contacts(lead)
        result.append(lead)
    return result[:limit]


def collect_leads(
    city: str,
    niche: str,
    sources: list[str],
    limit: int,
    on_status: Callable[[str], None] | None = None,
    start_page: int = 1,
) -> list[dict[str, Any]]:
    normalized_sources = [source.lower().strip() for source in sources]
    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    per_source_limit = max(1, limit)
    for source in normalized_sources:
        try:
            if source == "2gis":
                collected.extend(collect_2gis(city, niche, per_source_limit, on_status, start_page))
            elif source in {"yandex", "яндекс", "яндекс карты"}:
                collected.extend(collect_yandex(city, niche, per_source_limit, on_status))
            else:
                errors.append(f"Источник {source} пока не поддерживается")
        except Exception as error:  # noqa: BLE001 - return partial results when one source is unavailable
            errors.append(f"{source}: {error}")
    unique: dict[str, dict[str, Any]] = {}
    for lead in collected:
        identity = business_identity_key(lead)
        if identity.strip("|"):
            unique[identity] = lead
    result = list(unique.values())[: max(1, limit * len(normalized_sources))]
    if not result and errors:
        raise RuntimeError("; ".join(errors))
    if on_status and errors:
        on_status(f"Часть источников недоступна: {'; '.join(errors)[:140]}")
    return result


def load_2gis_json(path: Path, city: str, niche: str, limit: int) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    items = payload.get("items", []) if isinstance(payload, dict) else payload
    leads: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean((item.get("name_ex") or {}).get("primary") if isinstance(item.get("name_ex"), dict) else item.get("name"))
        if not name:
            continue
        lead = {
            "source": "2GIS",
            "city": _json_city(item) or city,
            "niche": niche,
            "name": name,
            "address": _clean(item.get("address_name")),
            "phone": _json_contact(item, "phone"),
            "website": _json_contact(item, "website"),
            "rating": _number(item.get("reviews", {}).get("general_rating") if isinstance(item.get("reviews"), dict) else None),
            "reviews": _integer(item.get("reviews", {}).get("general_review_count") if isinstance(item.get("reviews"), dict) else None),
            "card_url": _json_card_url(item),
            "social_url": _json_first_social(item),
            "contacts": _json_contacts(item),
            "branch_count": _json_branch_count(item),
        }
        leads.append(lead)
        if len(leads) >= limit:
            break
    return leads


def _json_city(item: dict[str, Any]) -> str:
    for div in item.get("adm_div") or []:
        if isinstance(div, dict) and div.get("type") == "city":
            return _clean(div.get("name"))
    return ""


def _json_contact(item: dict[str, Any], contact_type: str) -> str:
    for group in item.get("contact_groups") or []:
        if not isinstance(group, dict):
            continue
        for contact in group.get("contacts") or []:
            if isinstance(contact, dict) and contact.get("type") == contact_type:
                value = contact.get("url") if contact_type == "website" else contact.get("text")
                value = _clean(value or contact.get("value"))
                if value:
                    return value
    return ""


def _json_contacts(item: dict[str, Any]) -> list[dict[str, str]]:
    labels = {
        "phone": "Телефон", "email": "E-mail", "website": "Сайт",
        "telegram": "Telegram", "whatsapp": "WhatsApp", "vkontakte": "ВКонтакте",
        "instagram": "Instagram", "facebook": "Facebook", "youtube": "YouTube",
        "viber": "Viber", "linkedin": "LinkedIn",
    }
    contacts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for group in item.get("contact_groups") or []:
        if not isinstance(group, dict):
            continue
        for raw in group.get("contacts") or []:
            if not isinstance(raw, dict):
                continue
            contact_type = _clean(raw.get("type")).lower() or "other"
            value = _clean(raw.get("url") or raw.get("text") or raw.get("value"))
            if not value:
                continue
            identity_value = re.sub(r"\D+", "", value) if contact_type == "phone" else value.lower().split("?text=", 1)[0]
            identity = (contact_type, identity_value)
            if identity in seen:
                continue
            seen.add(identity)
            url = _clean(raw.get("url") or value)
            if contact_type == "whatsapp":
                url = url.split("?text=", 1)[0]
            contacts.append({
                "type": contact_type,
                "label": labels.get(contact_type, "Контакт"),
                "value": value,
                "url": url,
            })
    return contacts


def _json_first_social(item: dict[str, Any]) -> str:
    social_types = {"telegram", "vkontakte", "whatsapp", "instagram", "facebook", "youtube", "twitter", "linkedin", "pinterest"}
    for group in item.get("contact_groups") or []:
        for contact in group.get("contacts") or [] if isinstance(group, dict) else []:
            if not isinstance(contact, dict):
                continue
            value = _clean(contact.get("url") or contact.get("value") or contact.get("text"))
            if _clean(contact.get("type")).lower() in social_types or any(host in value.lower() for host in ("t.me", "telegram.", "vk.com", "wa.me", "whatsapp.")):
                return value
    return ""


def _flat_contacts(lead: dict[str, Any]) -> list[dict[str, str]]:
    contacts: list[dict[str, str]] = []
    phone = _clean(lead.get("phone"))
    website = _clean(lead.get("website"))
    social = _clean(lead.get("social_url"))
    if phone:
        contacts.append({"type": "phone", "label": "Телефон", "value": phone, "url": phone})
    if website:
        contacts.append({"type": "website", "label": "Сайт", "value": website, "url": website})
    if social:
        lowered = social.lower()
        contact_type = "telegram" if "t.me/" in lowered or "telegram." in lowered else "whatsapp" if "wa.me/" in lowered or "whatsapp." in lowered else "other"
        contacts.append({"type": contact_type, "label": "Telegram" if contact_type == "telegram" else "WhatsApp" if contact_type == "whatsapp" else "Соцсеть", "value": social, "url": social})
    return contacts


def _json_card_url(item: dict[str, Any]) -> str:
    value = _clean(item.get("url"))
    if value:
        return value
    item_id = _clean(item.get("id"))
    if item_id:
        return f"https://2gis.ru/firm/{item_id.split('_', 1)[0]}"
    return ""


def _json_branch_count(item: dict[str, Any]) -> int | None:
    for key in ("branch_count", "branches_count", "filials_count"):
        value = _integer(item.get(key))
        if value:
            return value
    return None


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ".")) if value not in (None, "") else None
    except ValueError:
        return None


def _integer(value: Any) -> int | None:
    match = re.search(r"\d+", _clean(value).replace(" ", ""))
    return int(match.group(0)) if match else None
