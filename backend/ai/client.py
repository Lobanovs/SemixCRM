from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .settings import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    resolved_settings,
)

logger = logging.getLogger(__name__)

JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class AiDisabledError(RuntimeError):
    """Ключ не задан: раздел должен молча выключиться, а не сломаться."""


class AiError(RuntimeError):
    """Модель не ответила или ответила не тем."""


@dataclass(frozen=True)
class AiSettings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = DEFAULT_TIMEOUT

    @property
    def enabled(self) -> bool:
        return bool(self.api_key.strip())


def load_settings() -> AiSettings:
    """Читает актуальные локальные настройки при каждом AI-запросе."""

    effective = resolved_settings()
    return AiSettings(
        api_key=str(effective["api_key"]),
        base_url=str(effective["base_url"]),
        model=str(effective["model"]),
        timeout=float(effective["timeout"]),
    )


def extract_json(raw: str) -> dict[str, Any]:
    """Достаёт объект из ответа модели.

    Модели любят обернуть JSON в ```json или добавить фразу до и после,
    поэтому берём самый внешний блок в фигурных скобках.
    """

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = JSON_BLOCK.search(text)
    if match is None:
        raise AiError("Модель вернула ответ без JSON")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise AiError(f"Не удалось разобрать JSON из ответа модели: {error}") from error


class AiClient:
    """Тонкая обёртка над chat/completions."""

    def __init__(
        self,
        settings: AiSettings | None = None,
        transport: Callable[..., httpx.Response] | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        # Точка подмены для тестов: живые вызовы стоят денег и времени.
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        if self._transport is not None:
            return self._transport(payload)
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.settings.timeout) as client:
            return client.post(f"{self.settings.base_url}/chat/completions", headers=headers, json=payload)

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        max_tokens: int = 1600,
        *,
        json_mode: bool = False,
    ) -> str:
        if not self.enabled:
            raise AiDisabledError("Не задан OPENCODE_API_KEY")
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.settings.model.casefold().startswith("mimo-"):
            # MiMo по умолчанию может потратить весь лимит на reasoning_content
            # и вернуть content=null. Для структурированных CRM-задач нужен итог.
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            response = self._post(payload)
            if response.status_code >= 500:
                logger.warning(
                    "OpenCode Go вернул временную ошибку %s, повторяю запрос один раз",
                    response.status_code,
                )
                response = self._post(payload)
        except httpx.HTTPError as error:
            raise AiError(f"Модель недоступна: {error}") from error
        if response.status_code == 401:
            raise AiError("Ключ OpenCode отклонён (401). Проверьте OPENCODE_API_KEY.")
        if response.status_code == 429:
            raise AiError("Лимит запросов исчерпан (429). Попробуйте позже.")
        if response.status_code >= 400:
            raise AiError(f"Модель вернула ошибку {response.status_code}: {response.text[:200]}")
        data = response.json()
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise AiError("Неожиданный формат ответа модели") from error
        content = message.get("content")
        if content is None:
            if message.get("reasoning_content") and choice.get("finish_reason") == "length":
                raise AiError(
                    "Модель исчерпала лимит ответа: лимит ответа ушёл на внутреннее рассуждение. "
                    "Повторите запрос или выберите другую модель."
                )
            raise AiError("Модель вернула ответ без итогового текста")
        if not isinstance(content, str) or not content.strip():
            raise AiError("Модель вернула пустой ответ")
        return content

    def complete_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        max_tokens: int = 1600,
        *,
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Просит JSON и один раз повторяет, если разбор не удался."""

        def parse_and_validate(raw: str) -> dict[str, Any]:
            payload = extract_json(raw)
            if validate is not None:
                validate(payload)
            return payload

        raw = self.complete(
            system,
            user,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            return parse_and_validate(raw)
        except AiError as first_error:
            logger.warning("Ответ модели не разобрался, повторяю строже: %s", first_error)
            strict = (
                f"{user}\n\n"
                f"Ошибка предыдущего ответа: {first_error}. "
                "Исправь её и верни ТОЛЬКО валидный JSON-объект "
                "без пояснений, без markdown и без текста до или после него."
            )
            retry = self.complete(
                system,
                strict,
                temperature=0.2,
                max_tokens=max_tokens,
                json_mode=True,
            )
            return parse_and_validate(retry)
