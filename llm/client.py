"""
Фабрика LLM-клиента. Оба бэкенда используют openai SDK.

Использование:
    from llm.client import parse_intent
    intent = await parse_intent("Отметь Петрова как оплатившего")
"""

import json
import logging
import re

from openai import AsyncOpenAI

from config import LLMBackend, settings
from llm.intents import SheetIntent
from llm.prompts import SYSTEM_PARSE_INTENT

log = logging.getLogger(__name__)


def _make_client() -> AsyncOpenAI:
    if settings.llm_backend == LLMBackend.OPENAI:
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


def _active_model() -> str:
    if settings.llm_backend == LLMBackend.OPENAI:
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


# Синглтон клиента (создаётся один раз при импорте модуля)
_client: AsyncOpenAI = _make_client()


async def parse_intent(user_text: str) -> SheetIntent:
    """
    Отправляет user_text в LLM и возвращает распознанный SheetIntent.
    При сетевых / парсинг ошибках возвращает intent с action=unknown.
    """
    model = _active_model()
    log.debug("LLM [%s/%s] запрос: %r", settings.llm_backend, model, user_text[:120])

    try:
        response = await _client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PARSE_INTENT},
                {"role": "user", "content": user_text},
            ],
            temperature=0,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content or ""
        log.debug("LLM ответ: %s", raw[:300])

        cleaned = _extract_json(raw)
        data = _normalize_action(json.loads(cleaned))
        intent = SheetIntent.model_validate(data)
        log.info("Разобран интент: action=%s | %s", intent.action, intent.raw_intent)
        return intent

    except json.JSONDecodeError as exc:
        log.error("LLM вернул невалидный JSON: %s | raw=%r", exc, raw[:200])
    except Exception as exc:
        log.error("Ошибка LLM-запроса: %s", exc)

    return SheetIntent(action="unknown", raw_intent="ошибка парсинга")
