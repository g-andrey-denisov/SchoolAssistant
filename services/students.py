"""Бизнес-логика работы с учениками (лист «Контакты»)."""

import logging
from datetime import date

from sheets.client import get_client
from sheets.schema import (
    COL_BIRTHDAY, COL_NOTE, COL_PARENT_NAME,
    COL_PARENT_PHONE, COL_STUDENT, INACTIVE_MARKER, CONTACTS_COLUMNS,
)
from utils.fuzzy import find_best_with_ambiguity

log = logging.getLogger(__name__)


def _is_inactive(row: dict) -> bool:
    return INACTIVE_MARKER in row.get(COL_NOTE, "").lower()


async def get_all_students() -> list[dict]:
    return await get_client().get_contacts()


async def get_active_students() -> list[dict]:
    return [s for s in await get_all_students() if not _is_inactive(s)]


async def resolve_student(
    query: str,
) -> tuple[str | None, int | None, list[str]]:
    """
    Нечёткий поиск. Возвращает (ФИО, row_num, [варианты]).
    Если однозначно: (ФИО, row_num, []).  Неоднозначно: (None, None, [варианты]).
    Не найден: (None, None, []).
    """
    indexed = await get_client().get_contacts_indexed()
    names = [row[COL_STUDENT] for _, row in indexed]
    best, ambiguous = find_best_with_ambiguity(query, names)
    if best:
        for row_num, row in indexed:
            if row[COL_STUDENT] == best:
                return best, row_num, []
    return None, None, ambiguous


async def add_student(data: dict) -> str:
    """data содержит ключи COL_STUDENT, COL_BIRTHDAY, COL_PARENT_NAME, COL_PARENT_PHONE."""
    name = data.get(COL_STUDENT, "?")
    await get_client().append_contact(data)
    await get_client().append_finance_student_row(name)
    log.info("Добавлен ученик: %s", name)
    return f"✅ Ученик <b>{name}</b> добавлен в класс."


async def mark_inactive(student_name: str, row_num: int) -> str:
    current = await get_all_students()
    student = next((s for s in current if s[COL_STUDENT] == student_name), None)
    existing_note = student.get(COL_NOTE, "").strip() if student else ""

    if INACTIVE_MARKER in existing_note.lower():
        return f"<b>{student_name}</b> уже помечен как «не ходит»."

    new_note = f"{existing_note}; {INACTIVE_MARKER}".lstrip("; ") if existing_note else INACTIVE_MARKER
    await get_client().update_contact_cell(row_num, COL_NOTE, new_note)
    log.info("Помечен неактивным: %s", student_name)
    return f"✅ <b>{student_name}</b> помечен как «не ходит»."


async def delete_student(student_name: str, row_num: int) -> str:
    await get_client().delete_contact_row(row_num)
    await get_client().delete_finance_student_row(student_name)
    log.info("Удалён ученик: %s", student_name)
    return f"🗑 Ученик <b>{student_name}</b> удалён из класса."


async def format_student_list(
    include_birthdays: bool = False,
    include_ages: bool = False,
    active_only: bool = False,
) -> str:
    from utils.dates import calculate_age, parse_date

    students = await get_all_students()
    if active_only:
        students = [s for s in students if not _is_inactive(s)]

    if not students:
        return "Список класса пуст."

    lines = []
    for i, s in enumerate(students, 1):
        name = s.get(COL_STUDENT, "—")
        inactive_mark = " <i>(не ходит)</i>" if _is_inactive(s) else ""

        extra = ""
        if include_birthdays or include_ages:
            bday_str = s.get(COL_BIRTHDAY, "").strip()
            bday = parse_date(bday_str) if bday_str else None
            parts = []
            if include_birthdays and bday_str:
                parts.append(bday_str)
            if include_ages and bday and bday.year != date.today().year:
                parts.append(f"{calculate_age(bday)} лет")
            if parts:
                extra = f" ({', '.join(parts)})"

        lines.append(f"{i}. <b>{name}</b>{extra}{inactive_mark}")

    header = f"📋 Список класса ({len(students)} чел.):"
    return header + "\n" + "\n".join(lines)


async def count_students() -> tuple[int, int]:
    """Возвращает (всего, активных)."""
    students = await get_all_students()
    active = sum(1 for s in students if not _is_inactive(s))
    return len(students), active
