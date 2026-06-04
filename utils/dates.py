"""Парсинг дат, вычисление возраста и ближайших дней рождения."""

import re
from datetime import date


_PATTERNS = [
    re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"),   # DD.MM.YYYY
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"),           # YYYY-MM-DD (ISO)
    re.compile(r"^(\d{1,2})\.(\d{1,2})$"),              # DD.MM (без года)
]


def parse_date(s: str) -> date | None:
    """Возвращает date или None, если разобрать не удалось."""
    s = s.strip()

    m = _PATTERNS[0].match(s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None

    m = _PATTERNS[1].match(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    m = _PATTERNS[2].match(s)
    if m:
        try:
            today = date.today()
            return date(today.year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None

    return None


def days_until_birthday(bday: date) -> int:
    """Дней до следующего дня рождения (0 = сегодня)."""
    today = date.today()
    try:
        next_bday = bday.replace(year=today.year)
    except ValueError:
        # 29 февраля в невисокосный год
        next_bday = date(today.year, 3, 1)

    if next_bday < today:
        try:
            next_bday = bday.replace(year=today.year + 1)
        except ValueError:
            next_bday = date(today.year + 1, 3, 1)

    return (next_bday - today).days


def calculate_age(bday: date) -> int:
    """Текущий возраст (полных лет). Требует год рождения."""
    today = date.today()
    age = today.year - bday.year
    if (today.month, today.day) < (bday.month, bday.day):
        age -= 1
    return age


def will_turn_age(bday: date) -> int:
    """Сколько лет исполнится на следующем дне рождения."""
    today = date.today()
    next_year = today.year
    try:
        next_bday = bday.replace(year=next_year)
    except ValueError:
        next_bday = date(next_year, 3, 1)
    if next_bday <= today:
        next_year += 1
    return next_year - bday.year


def format_date(d: date, with_year: bool = True) -> str:
    if with_year:
        return d.strftime("%d.%m.%Y")
    return d.strftime("%d.%m")
