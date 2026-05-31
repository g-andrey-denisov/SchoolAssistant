"""Дни рождения (лист «Контакты»)."""

from datetime import date

from sheets.client import get_client
from sheets.schema import COL_BIRTHDAY, COL_STUDENT
from services.students import _is_inactive
from utils.text import esc
from utils.dates import (
    calculate_age, days_until_birthday, format_date, parse_date, will_turn_age,
)


async def upcoming_birthdays(days_ahead: int = 30) -> str:
    students = await get_client().get_contacts()
    upcoming = []

    for s in students:
        if _is_inactive(s):
            continue
        bday_str = s.get(COL_BIRTHDAY, "").strip()
        if not bday_str:
            continue
        bday = parse_date(bday_str)
        if bday is None:
            continue
        days = days_until_birthday(bday)
        if days <= days_ahead:
            has_year = len(bday_str) > 5  # "DD.MM" = 5 символов
            turns = will_turn_age(bday) if has_year else None
            upcoming.append((days, s[COL_STUDENT], bday, turns))

    if not upcoming:
        return f"Дней рождений в ближайшие {days_ahead} дней нет."

    upcoming.sort(key=lambda x: x[0])
    lines = []
    for days, name, bday, turns in upcoming:
        if days == 0:
            day_str = "🎂 сегодня!"
        elif days == 1:
            day_str = "завтра"
        else:
            day_str = f"через {days} дн."
        age_str = f" (исполнится {turns})" if turns else ""
        lines.append(f"  • <b>{esc(name)}</b> — {format_date(bday)} — {day_str}{age_str}")

    return (
        f"🎂 <b>Ближайшие дни рождения (до {days_ahead} дней):</b>\n" + "\n".join(lines)
    )


async def birthday_list(include_ages: bool = True) -> str:
    students = await get_client().get_contacts()
    today = date.today()
    rows = []
    no_bday = []

    for s in students:
        bday_str = s.get(COL_BIRTHDAY, "").strip()
        name = s[COL_STUDENT]
        if not bday_str:
            no_bday.append(name)
            continue
        bday = parse_date(bday_str)
        if bday is None:
            no_bday.append(name)
            continue
        has_year = len(bday_str) > 5
        days = days_until_birthday(bday)
        age = calculate_age(bday) if (has_year and bday.year != today.year) else None
        rows.append((days, name, bday_str, age))

    rows.sort(key=lambda x: x[0])
    lines = []
    for _, name, bday_str, age in rows:
        age_str = f", {age} лет" if (include_ages and age is not None) else ""
        lines.append(f"  • <b>{esc(name)}</b> — {bday_str}{age_str}")

    result = (
        f"📅 <b>Дни рождения класса ({len(rows)} из {len(students)}):</b>\n"
        + "\n".join(lines)
    )
    if no_bday:
        result += f"\n\n<i>Дата не указана: {', '.join(esc(x) for x in no_bday)}</i>"
    return result


_MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


async def birthdays_by_month() -> str:
    """Помесячная разбивка: под каждым месяцем — ученики с их датой рождения."""
    students = await get_client().get_contacts()
    by_month: dict[int, list[tuple[int, str, str]]] = {m: [] for m in range(1, 13)}
    no_bday: list[str] = []

    for s in students:
        name = s.get(COL_STUDENT, "").strip()
        if not name:
            continue
        bday_str = s.get(COL_BIRTHDAY, "").strip()
        bday = parse_date(bday_str) if bday_str else None
        if bday is None:
            no_bday.append(name)
            continue
        by_month[bday.month].append((bday.day, name, bday_str))

    blocks = []
    total = 0
    for m in range(1, 13):
        entries = by_month[m]
        if not entries:
            continue
        entries.sort(key=lambda x: x[0])
        total += len(entries)
        body = "\n".join(
            f"  • <b>{esc(name)}</b> — {bday_str}" for _, name, bday_str in entries
        )
        blocks.append(f"<b>{_MONTH_NAMES[m - 1]}</b> ({len(entries)}):\n{body}")

    if not blocks:
        return "Ни у кого не указана дата рождения."

    result = f"📅 <b>Дни рождения по месяцам ({total}):</b>\n\n" + "\n\n".join(blocks)
    if no_bday:
        result += f"\n\n<i>Дата не указана: {', '.join(esc(x) for x in no_bday)}</i>"
    return result
