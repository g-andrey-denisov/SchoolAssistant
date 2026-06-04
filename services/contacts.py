"""Поиск контактных данных родителей (лист «Контакты»)."""

from sheets.schema import COL_STUDENT, COL_PARENT_NAME, COL_PARENT_PHONE
from services.students import resolve_student
from utils.phones import format_phones
from utils.text import esc


async def get_phone(query: str) -> str:
    name, _, ambiguous = await resolve_student(query)
    if ambiguous:
        return "Уточните, кого имеете в виду:\n" + "\n".join(f"• {esc(n)}" for n in ambiguous)
    if name is None:
        return f"Ученик <b>«{esc(query)}»</b> не найден."

    from sheets.client import get_client
    students = await get_client().get_contacts()
    student = next((s for s in students if s[COL_STUDENT] == name), None)
    if student is None:
        return "Данные ученика не найдены."

    parent_name = student.get(COL_PARENT_NAME, "").strip()
    phones = format_phones(student.get(COL_PARENT_PHONE, "").strip())

    if not parent_name and not phones:
        return f"Контактные данные для <b>{esc(name)}</b> не заполнены."

    parts = [f"👤 Ученик: <b>{esc(name)}</b>"]
    if parent_name:
        parts.append(f"👨‍👩‍👧 Родитель: <b>{esc(parent_name)}</b>")
    if phones:
        for phone in phones:
            parts.append(f"📞 <b>{phone}</b>")
    else:
        parts.append("📞 Телефон не указан")

    return "\n".join(parts)
