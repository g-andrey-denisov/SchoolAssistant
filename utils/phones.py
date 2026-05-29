"""Форматирование номеров телефонов."""

import re


def format_phone(raw: str) -> str:
    """
    Приводит номер к виду +7(xxx)xxx-xxxx.

    Алгоритм:
      1. Убрать всё, кроме цифр и «+».
      2. Если не начинается с «+» — заменить первый символ на «+7».
      3. Следующие три цифры обернуть в круглые скобки.
      4. Через ещё три цифры поставить дефис.
    """
    if not raw or not raw.strip():
        return raw

    # Шаг 1: оставляем только цифры и «+»
    s = re.sub(r"[^\d+]", "", raw.strip())
    if not s:
        return raw

    # Шаг 2: если первый символ не «+», заменяем его на «+7»
    if not s.startswith("+"):
        only_digits = re.sub(r"\D", "", s)
        if len(only_digits) == 10:
            # 10 цифр без кода страны — добавляем «+7» перед ними
            s = "+7" + only_digits
        else:
            # 11+ цифр — первый символ (8 или 7) заменяем на «+7»
            s = "+7" + s[1:]

    # Цифровая часть после «+» и кода страны «7»
    digits = re.sub(r"\D", "", s[2:])   # всё, что идёт после «+» и кода страны

    if len(digits) < 10:
        return s  # нестандартный формат — возвращаем как есть

    # Шаги 3-4: +7(xxx)xxx-xxxx
    return f"+7({digits[0:3]}){digits[3:6]}-{digits[6:10]}"


# Разделители между несколькими номерами в одной ячейке
_SEPARATORS = re.compile(r"[,;/\n]+")


def format_phones(raw: str) -> list[str]:
    """
    Разбивает ячейку с одним или несколькими номерами и форматирует каждый.
    Возвращает список отформатированных номеров (пустые отбрасываются).
    """
    if not raw or not raw.strip():
        return []
    parts = _SEPARATORS.split(raw)
    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        formatted = format_phone(part)
        # Берём результат только если там реально есть цифры
        if formatted and re.search(r"\d", formatted):
            result.append(formatted)
    return result
