from __future__ import annotations

from typing import Any

from .profile import ExecutorProfile


MESSAGE_MIN_LENGTH = 70
MESSAGE_MAX_LENGTH = 260
TONE_LENGTHS = {
    "confident": (70, 260),
    "hard_sell": (70, 260),
    "expert": (70, 260),
}

SYSTEM_PROMPT = """Ты — консультативный B2B-продавец для малого бизнеса в России.
Ты пишешь только первое холодное сообщение владельцу в WhatsApp или Telegram.
Цель первого сообщения — не продать сайт, а получить честный короткий ответ о том,
как сейчас устроен один конкретный процесс.

ФОРМУЛА
Конкретный проверенный контекст + один вопрос о текущем процессе + лёгкий ответ.
— 70–260 символов.
— Одна или две короткие фразы после приветствия.
— Ровно один вопросительный знак; сообщение заканчивается вопросом.
— Вопрос должен быть таким, чтобы на него можно было ответить фактом или одной фразой.
— Не притворяйся клиентом и не скрывай деловую цель вымышленной историей.

ТРИ ДИАГНОСТИЧЕСКИХ УГЛА
confident — «Цены и информация»: как клиент узнаёт цены, услуги или детали.
hard_sell — «Запись и заявки»: как клиент записывается и куда поступает заявка.
expert — «Обработка обращений»: что происходит вечером, при пропущенном звонке
или когда администратор не успевает ответить.
Варианты должны различаться диагностируемым процессом, а не перестановкой слов.

ДОКАЗАТЕЛЬСТВА
— Используй только карточку, ручное наблюдение и переданные отзывы 2GIS.
— review_insight.evidence_ids содержит только переданные R1, R2 и так далее.
— Без отзывов нельзя писать, что ты их читал, или приписывать клиентам похвалу.
— Если отдельный сайт не указан, пиши «в карточке 2GIS не увидел отдельного сайта».
— Не объявляй потерю клиентов фактом и не выдумывай текущий процесс.

В ПЕРВОМ СООБЩЕНИИ ЗАПРЕЩЕНО
— Предлагать сайт, автоматизацию, сотрудничество или другую услугу.
— URL, портфолио, цена, рубли, сроки, демо, прототип, презентация или созвон.
— «Актуально?», «Интересно?», «Хотите?», ответ «да» и рекламные штампы.
— Несколько вопросов, сложный выбор или вопрос о покупке.
— Обращаться к получателю именем отправителя из блока «ОТПРАВИТЕЛЬ».

ФОРМАТ ОТВЕТА
Верни ТОЛЬКО валидный JSON-объект без markdown и пояснений:
{
  "analysis": {
    "signal": "проверенный контекст",
    "problem": "процесс, который стоит уточнить",
    "opportunity": "почему ответ поможет продолжить диагностику"
  },
  "review_insight": {
    "summary": "деталь из отзывов или пустая строка",
    "evidence_ids": ["R1"]
  },
  "variants": [
    {
      "tone": "confident",
      "title": "Цены и информация",
      "text": "70–260 символов"
    },
    {
      "tone": "hard_sell",
      "title": "Запись и заявки",
      "text": "70–260 символов"
    },
    {
      "tone": "expert",
      "title": "Обработка обращений",
      "text": "70–260 символов"
    }
  ],
  "follow_up": ""
}"""


def _yes_no(value: Any) -> str:
    return "да" if value else "нет"


def build_client_message_prompt(
    client: dict[str, Any],
    profile: ExecutorProfile,
    manual_observation: str = "",
    review_evidence: list[dict[str, str]] | None = None,
) -> str:
    """Собирает пользовательскую часть промпта из реальных полей карточки."""

    contacts = client.get("contacts") or []
    channels = sorted({str(item.get("type") or "") for item in contacts if item.get("type")})
    website = str(client.get("website") or "").strip()
    has_real_site = bool(website) and not any(
        marker in website.lower() for marker in ("t.me", "wa.me", "vk.com", "instagram", "facebook")
    )
    reasons = client.get("lead_score_reasons") or []
    rating = client.get("rating")
    reviews = client.get("reviews")

    facts = [
        f"Название: {client.get('name') or 'не указано'}",
        f"Ниша: {client.get('niche') or client.get('category') or 'не указана'}",
        f"Город: {client.get('city') or 'не указан'}",
        f"Адрес: {client.get('address') or 'не указан'}",
        f"Рейтинг: {rating if rating is not None else 'нет данных'}",
        f"Отзывов: {reviews if reviews is not None else 'нет данных'}",
        f"Полноценный сайт: {_yes_no(has_real_site)}" + (f" ({website})" if website else ""),
        f"Каналы связи: {', '.join(channels) if channels else 'только телефон'}",
        f"Оценка лида: {client.get('lead_score')} из 23, соответствие {client.get('match_score')}%",
    ]
    if reasons:
        facts.append(f"Почему лид интересен: {'; '.join(str(item) for item in reasons)}")
    if client.get("pain"):
        facts.append(f"Предварительная гипотеза о боли: {client['pain']}")
    if client.get("branch_count"):
        facts.append(f"Филиалов: {client['branch_count']}")

    observation = manual_observation.strip()
    reviews = review_evidence or []
    observation_block = (
        f"\n\nРУЧНОЕ НАБЛЮДЕНИЕ (проверено отправителем)\n{observation}"
        if observation
        else "\n\nРУЧНОЕ НАБЛЮДЕНИЕ\nне указано"
    )
    reviews_block = (
        "\n\nОТЗЫВЫ 2GIS (цитировать дословно не нужно; используй только подтверждённые детали)\n"
        + "\n".join(f"[{item['id']}] {item['text']}" for item in reviews)
        if reviews
        else "\n\nОТЗЫВЫ 2GIS\nне удалось получить — не утверждай, что читал отзывы"
    )

    return (
        "КАРТОЧКА КОМПАНИИ\n"
        + "\n".join(facts)
        + observation_block
        + reviews_block
        + f"\n\nОТПРАВИТЕЛЬ\nИмя отправителя: {profile.name}"
        + "\n\nНапиши разбор и три разных диагностических вопроса по системной инструкции."
    )
