from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote


ROOT_DIR = Path(__file__).resolve().parents[1]
LEADHUNT_DIR = Path(os.getenv("LEADHUNT_ROOT", r"C:\Users\Admin\Desktop\LeadHunt"))
PARSER2GIS_DIR = LEADHUNT_DIR / "_external" / "parser-2gis"
PARSER2GIC_DIR = Path(os.getenv("PARSER2GIC_ROOT", r"C:\Users\Admin\Desktop\parser2gic"))
PARSE_RUNNER = PARSER2GIC_DIR / "parse_runner.py"
OUTPUT_DIR = ROOT_DIR / "backend" / "data" / "parser_output"
CITIES_FILE = PARSER2GIS_DIR / "parser_2gis" / "data" / "cities.json"


def resolve_city_code(city: str) -> str:
    clean_city = city.strip().lower()
    if not clean_city:
        raise ValueError("Укажите город для парсинга")
    if CITIES_FILE.exists():
        try:
            payload = json.loads(CITIES_FILE.read_text(encoding="utf-8"))
            for item in payload if isinstance(payload, list) else []:
                if str(item.get("name", "")).strip().lower() == clean_city and item.get("code"):
                    return str(item["code"])
        except (OSError, json.JSONDecodeError):
            pass
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


def _python_command() -> list[str]:
    configured = os.getenv("LEADHUNT_PYTHON", "").strip()
    if configured:
        return [configured]
    # The old LeadHunt venv points to a removed Python 3.13 installation. The
    # current Python launcher is deliberately used instead, where parser-2gis
    # is installed and its pydantic 1.x dependency is isolated from FastAPI.
    launcher = shutil.which("py")
    if launcher:
        return [launcher, "-3"]
    return [sys.executable]


def collect_2gis(city: str, niche: str, limit: int, on_status: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    if not PARSE_RUNNER.exists():
        raise FileNotFoundError(f"Не найден запускатель LeadHunt: {PARSE_RUNNER}")
    if not PARSER2GIS_DIR.exists():
        raise FileNotFoundError(f"Не найден parser-2gis: {PARSER2GIS_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"leadhunt_{uuid.uuid4().hex[:10]}.json"
    city_code = resolve_city_code(city)
    url = f"https://2gis.ru/{city_code}/search/{quote(niche, safe='')}/filters/sort=name"
    cmd = _python_command() + [
        str(PARSE_RUNNER), "-i", url, "-o", str(output_path), "-f", "json",
        "--chrome.headless", os.getenv("LEADHUNT_HEADLESS", "yes"),
        "--chrome.start-maximized", "yes",
        "--chrome.silent-browser", "yes",
        "--parser.max-records", str(max(1, min(int(limit), 200))),
        "--writer.verbose", "yes",
    ]
    if on_status:
        on_status(f"Открываю 2GIS: {city}, {niche}")
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(PARSER2GIS_DIR)})
    timeout = max(180, min(600, 20 + int(limit) * 12))
    try:
        completed = subprocess.run(
            cmd, cwd=str(PARSER2GIC_DIR), env=environment, text=True,
            encoding="utf-8", errors="replace", stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=timeout, check=False,
        )
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
    return load_2gis_json(output_path, city, niche, limit)


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
