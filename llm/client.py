"""
Фабрика LLM-клиента. Оба бэкенда используют openai SDK.

Использование:
    from llm.client import parse_intent
    intent = await parse_intent("Отметь Петрова как оплатившего")
"""

import json
import logging
import re

from openai import APIError, AsyncOpenAI
from pydantic import ValidationError

from config import LLMBackend, settings
from llm.intents import SheetIntent
from llm.prompts import SYSTEM_PARSE_INTENT

log = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    """Все LLM-бэкенды из очереди недоступны (сеть/таймаут/API-ошибка).

    Не путать с «не понял запрос» — та ситуация возвращается как
    SheetIntent(action="unknown"), а не поднимается исключением.
    """


def _make_client(backend: LLMBackend) -> AsyncOpenAI:
    if backend == LLMBackend.OPENAI:
        return AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout,
        )
    # LM Studio — OpenAI-совместимый сервер, api_key может быть любым
    return AsyncOpenAI(
        base_url=settings.lmstudio_base_url,
        api_key="lm-studio",
        timeout=settings.llm_timeout,
    )


def _active_model(backend: LLMBackend) -> str:
    if backend == LLMBackend.OPENAI:
        return settings.openai_model
    return settings.lmstudio_model


def _extract_json(raw: str) -> str:
    """Вытаскивает JSON из ответа LLM, который может быть обёрнут в ```json ... ```."""
    # Убираем markdown-блоки вида ```json или ```
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text.strip())
    # На случай если JSON «плавает» среди текста — берём первый {...}
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


# Алиасы: сокращённые имена, которые возвращают слабые LLM-модели → правильные значения
_ACTION_ALIASES: dict[str, str] = {
    "expense_list":              "report_expenses_list",
    "expenses_list":             "report_expenses_list",
    "report_expense_list":       "report_expenses_list",
    "contribution_list":         "report_contributions_list",
    "contributions_list":        "report_contributions_list",
    "report_contribution_list":  "report_contributions_list",
    "balance":                   "report_balance",
    "finance":                   "report_full",
    "report_finance":            "report_full",
    "class_finance":             "report_class_finance",
    "contributions_total":       "report_contributions_total",
    "expenses_total":            "report_expenses_total",
    "paid":                      "report_paid",
    "contributions_by_student":  "report_contributions_by_student",
}


def _normalize_action(data: dict) -> dict:
    """Приводит сокращённые имена action к каноническим значениям IntentAction."""
    action = data.get("action", "")
    if isinstance(action, str):
        data["action"] = _ACTION_ALIASES.get(action, action)
    return data


# Клиенты создаются лениво и кешируются: конструктор AsyncOpenAI падает,
# если для бэкенда не задан api_key (напр. OPENAI_API_KEY пуст, а используется
# только LM Studio) — эйгерная инициализация всех бэкендов сразу сломала бы
# запуск бота в такой конфигурации.
_clients: dict[LLMBackend, AsyncOpenAI] = {}


def _get_client(backend: LLMBackend) -> AsyncOpenAI:
    client = _clients.get(backend)
    if client is None:
        client = _make_client(backend)
        _clients[backend] = client
    return client


# Некоторые модели (o1/o3/gpt-5-«reasoning» и т.п.) отклоняют отдельные
# параметры выборки, которые обычные chat-модели прекрасно принимают —
# например, фиксируют temperature=1 и не разрешают его переопределять.
# Вместо того чтобы перечислять такие модели вручную, при ошибке вида
# "Unsupported value/parameter: '<param>'" просто убираем этот параметр
# из запроса и пробуем ещё раз.
_MAX_PARAM_DROP_RETRIES = 4


async def _create_completion(client: AsyncOpenAI, model: str, user_text: str, **kwargs) -> str:
    for _ in range(_MAX_PARAM_DROP_RETRIES):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PARSE_INTENT},
                    {"role": "user", "content": user_text},
                ],
                **kwargs,
            )
            return response.choices[0].message.content or ""
        except APIError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            param = body.get("param")
            code = body.get("code")
            if code in ("unsupported_parameter", "unsupported_value") and param in kwargs:
                log.warning(
                    "Модель %s не поддерживает параметр %r (%s) — повтор без него", model, param, code
                )
                kwargs.pop(param)
                continue
            raise
    raise RuntimeError(f"Не удалось подобрать параметры запроса к модели {model}")


async def parse_intent(user_text: str) -> SheetIntent:
    """
    Отправляет user_text в LLM и возвращает распознанный SheetIntent.

    Если llm_fallback_enabled=True, при недоступности очередного бэкенда
    (сеть, таймаут, ошибка API) запрос повторяется на следующем бэкенде из
    settings.llm_fallback_backends. Если все бэкенды недоступны — поднимается
    LLMUnavailableError.

    Если бэкенд ответил, но не валидным JSON/интентом — это НЕ недоступность,
    а «не поняла запрос»: сразу возвращаем SheetIntent(action="unknown") без
    перебора остальных бэкендов.
    """
    backends = settings.llm_fallback_backends if settings.llm_fallback_enabled else [settings.llm_backend]
    errors: list[str] = []

    for backend in backends:
        model = _active_model(backend)
        log.debug("LLM [%s/%s] запрос: %r", backend, model, user_text[:120])

        # Новые модели OpenAI (o1/o3/gpt-5 и т.п.) отклоняют устаревший
        # max_tokens («Unsupported parameter») и требуют max_completion_tokens.
        # LM Studio и другие OpenAI-совместимые серверы, наоборот, обычно
        # понимают только старый max_tokens.
        token_limit_kwarg = (
            {"max_completion_tokens": 1024}
            if backend == LLMBackend.OPENAI
            else {"max_tokens": 1024}
        )

        try:
            client = _get_client(backend)
            raw = await _create_completion(
                client, model, user_text, temperature=0, **token_limit_kwarg
            )
        except Exception as exc:
            # Сетевые ошибки, таймаут, ошибка API, отсутствие api_key и т.п. —
            # бэкенд недоступен, пробуем следующий из очереди.
            log.error("LLM-бэкенд недоступен [%s/%s]: %s", backend, model, exc)
            errors.append(f"{backend}: {exc}")
            continue

        log.debug("LLM ответ: %s", raw[:300])

        try:
            cleaned = _extract_json(raw)
            data = _normalize_action(json.loads(cleaned))
            intent = SheetIntent.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            # Модель ответила, но не валидным интентом — это реальное «не понял запрос».
            log.error("LLM вернул некорректный интент [%s/%s]: %s | raw=%r", backend, model, exc, raw[:200])
            return SheetIntent(action="unknown", raw_intent="ошибка парсинга")

        log.info("Разобран интент [%s]: action=%s | %s", backend, intent.action, intent.raw_intent)
        return intent

    raise LLMUnavailableError("; ".join(errors))
