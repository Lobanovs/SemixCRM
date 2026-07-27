from __future__ import annotations

import re

from .models import FreelanceOrder, FreelanceSettings


# Максимум очков. Шкала объяснимая: каждое очко подписано причиной, как у лидов.
FREELANCE_SCORE_MAX = 20

# Профильная работа: то, что Семён реально делает и берёт в работу.
CORE_WORK = (
    "сайт", "лендинг", "landing", "веб-приложение", "веб приложение", "webapp", "web-приложение",
    "интернет-магазин", "магазин на", "crm", "erp", "личный кабинет", "админк", "дашборд", "dashboard",
    "бот", "bot", "телеграм", "telegram", "автоматизац", "интеграц", "api", "парсер", "скрипт",
    "веб", "web", "mvp", "интерфейс", "фронт", "сервис на", "портал",
    "разработ", "программист", "верстк", "вёрстк", "фронтенд", "frontend", "бэкенд", "backend",
    "fullstack", "full-stack", "доработ", "дописать", "багфикс", "исправить код", "рефактор",
    "телеграм-бот", "чат-бот", "квиз", "калькулятор на сайт", "форма на сайт",
)

# Знакомый стек — заказ понятен без изучения новой технологии.
KNOWN_STACK = (
    "react", "next.js", "nextjs", "vue", "nuxt", "svelte", "astro", "typescript", "javascript",
    "node.js", "nodejs", "python", "fastapi", "django", "flask", "aiogram", "telegram bot api",
    "tailwind", "vite", "wordpress", "tilda", "тильда", "bitrix", "битрикс", "webflow",
    "postgres", "postgresql", "sqlite", "mysql", "supabase", "firebase", "docker",
    "html", "css", "figma", "rest", "graphql", "playwright", "selenium",
)

# Явно не его работа: такие заказы не должны попадать наверх списка.
OFF_PROFILE = (
    "курьер", "доставка еды", "уборк", "клининг", "грузоперевоз", "переезд", "грузчик",
    "репетитор", "няня", "сиделк", "маникюр", "педикюр", "парикмахер", "массаж", "косметолог",
    "ремонт квартир", "натяжн", "сантехник", "электрик", "плиточник", "обои", "штукатур",
    "шиномонтаж", "автомойк", "выгул собак", "сборка мебели", "муж на час",
    "написание диплом", "курсов", "реферат", "эссе", "контрольн",
    "продажи по телефону", "холодные звонки", "оператор call", "колл-центр",
)

# Признаки заказов, на которые не стоит тратить время.
RED_FLAGS = (
    "за отзыв", "бесплатно", "за портфолио", "тестовое без оплаты", "процент с продаж",
    "оплата после", "нужен соучредитель", "долю в проекте",
)

LOW_BUDGET_LIMIT = 3000
DECENT_BUDGET = 30000


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold().replace("ё", "е")).strip()


def _hits(haystack: str, needles: tuple[str, ...]) -> list[str]:
    """Ищет маркеры с начала слова.

    Простое вхождение подстроки давало ложные объяснения: «бот» находился внутри
    «разработка», «обработки» и «работа». Окончания при этом остаются свободными,
    поэтому «сайт» по-прежнему находит «сайта», а «разработ» — «разработку».
    """

    found: list[str] = []
    for needle in needles:
        normalized = _normalize(needle)
        if not normalized:
            continue
        if re.search(rf"(?<![a-zа-я0-9]){re.escape(normalized)}", haystack):
            found.append(needle)
    return found


def score_order(order: FreelanceOrder, settings: FreelanceSettings) -> tuple[int, list[str], int]:
    """Объяснимый рейтинг заказа: очки, причины и процент соответствия.

    Шкала построена вокруг разработки: профильная работа и знакомый стек весят
    больше всего, непрофильные категории обнуляют оценку целиком.
    """

    title = _normalize(order.title)
    body = _normalize(" ".join((order.description, *order.categories, *order.tags)))
    everything = f"{title} {body}"

    excluded = _hits(everything, tuple(settings.excluded_keywords))
    if excluded:
        return 0, [f"Стоп-слово: {excluded[0]}"], 0

    off_profile = _hits(everything, OFF_PROFILE)
    if off_profile:
        return 0, [f"Не ваш профиль: {off_profile[0]}"], 0

    score = 0
    reasons: list[str] = []

    core_in_title = _hits(title, CORE_WORK)
    core_in_body = [item for item in _hits(body, CORE_WORK) if item not in core_in_title]
    if core_in_title:
        score += 6
        reasons.append(f"Профильная задача в названии: {', '.join(core_in_title[:3])}")
    elif core_in_body:
        score += 3
        reasons.append(f"Профильная задача в описании: {', '.join(core_in_body[:3])}")

    stack = _hits(everything, KNOWN_STACK)
    if stack:
        score += 3
        reasons.append(f"Знакомый стек: {', '.join(stack[:4])}")

    personal = _hits(everything, tuple(settings.keywords))
    if personal:
        score += 2
        reasons.append(f"Ваши ключевые слова: {', '.join(personal[:3])}")

    budget = order.budget_max if order.budget_max is not None else order.budget_min
    threshold = settings.min_budget or DECENT_BUDGET
    if budget is not None:
        score += 2
        reasons.append(f"Бюджет указан: {budget:,} ₽".replace(",", " "))
        if budget >= threshold:
            score += 3
            reasons.append(f"Бюджет от {threshold:,} ₽".replace(",", " "))
        elif budget < LOW_BUDGET_LIMIT:
            score -= 3
            reasons.append(f"Бюджет ниже {LOW_BUDGET_LIMIT:,} ₽ — обычно не окупается".replace(",", " "))

    flags = _hits(everything, RED_FLAGS)
    if flags:
        score -= 4
        reasons.append(f"Тревожный сигнал: {flags[0]}")

    if order.customer.strip():
        score += 1
        reasons.append("Заказчик указан")

    if not reasons:
        reasons.append("Нет признаков профильной задачи")

    score = max(0, min(score, FREELANCE_SCORE_MAX))
    return score, reasons, round(score / FREELANCE_SCORE_MAX * 100)
