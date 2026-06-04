"""
Бизнес-логика взносов и трат (лист «Финансы»).

Модель данных:
  Колонка «Взнос: <назначение>» — что ученик заплатил (значения > 0)
  Колонка «Трата: <назначение>» — что потрачено на ученика (значения > 0)
  Остаток кассы = Σ взносов − Σ трат
"""

import logging

from sheets.client import get_client
from sheets.schema import CONTRIB_PREFIX, EXPENSE_PREFIX, COL_STUDENT
from services.students import get_active_students, resolve_student
from utils.text import esc

log = logging.getLogger(__name__)


# ── Взносы ────────────────────────────────────────────────────────────────

async def add_contribution(
    student_query: str, purpose: str, amount: float
) -> tuple[str | None, str]:
    """Фиксирует взнос ученика. Возвращает (ФИО|None, сообщение)."""
    name, _, ambiguous = await resolve_student(student_query)
    if ambiguous:
        return None, "Уточните:\n" + "\n".join(f"• {esc(n)}" for n in ambiguous)
    if name is None:
        return None, f"Ученик <b>«{esc(student_query)}»</b> не найден."

    col = CONTRIB_PREFIX + purpose
    await get_client().batch_update_finance_column(col, {name: amount})
    log.info("Взнос: %s | %s | +%.2f", name, col, amount)
    return name, f"✅ <b>{esc(name)}</b> сдал(а) <b>{amount:.0f} руб.</b> на «{esc(purpose)}»."


async def contribution_all_students(purpose: str, per_student_amount: float) -> str:
    """Весь класс сдал по per_student_amount — добавляет взнос каждому активному ученику."""
    active = await get_active_students()
    if not active:
        return "⚠️ Нет активных учеников."
    n = len(active)
    col = CONTRIB_PREFIX + purpose
    deltas = {s[COL_STUDENT]: per_student_amount for s in active}
    await get_client().batch_update_finance_column(col, deltas)
    total = per_student_amount * n
    log.info("Взнос all: %s | %.2f × %d = %.2f", col, per_student_amount, n, total)
    return (
        f"✅ Взнос «{esc(purpose)}» записан всем:\n"
        f"  На каждого: <b>{per_student_amount:.2f} руб.</b>\n"
        f"  Учеников: {n}\n"
        f"  Итого: <b>{total:.2f} руб.</b>"
    )


# ── Траты ─────────────────────────────────────────────────────────────────

async def split_expense(purpose: str, total_amount: float) -> str:
    """Делит общую сумму поровну среди активных учеников."""
    active = await get_active_students()
    if not active:
        return "⚠️ Нет активных учеников."
    n = len(active)
    per_person = round(total_amount / n, 2)
    col = EXPENSE_PREFIX + purpose
    deltas = {s[COL_STUDENT]: per_person for s in active}
    await get_client().batch_update_finance_column(col, deltas)
    log.info("Трата split: %s | %.2f / %d = %.2f", col, total_amount, n, per_person)
    return (
        f"✅ Трата «{esc(purpose)}» распределена:\n"
        f"  Итого: <b>{total_amount:.0f} руб.</b>\n"
        f"  Учеников: {n}\n"
        f"  На каждого: <b>{per_person:.2f} руб.</b>"
    )


async def expense_per_student(purpose: str, per_student_amount: float) -> str:
    """Каждому активному ученику записывается фиксированная сумма."""
    active = await get_active_students()
    if not active:
        return "⚠️ Нет активных учеников."
    n = len(active)
    col = EXPENSE_PREFIX + purpose
    deltas = {s[COL_STUDENT]: per_student_amount for s in active}
    await get_client().batch_update_finance_column(col, deltas)
    total = per_student_amount * n
    log.info("Трата per_student: %s | %.2f × %d = %.2f", col, per_student_amount, n, total)
    return (
        f"✅ Трата «{esc(purpose)}» записана каждому:\n"
        f"  На каждого: <b>{per_student_amount:.2f} руб.</b>\n"
        f"  Учеников: {n}\n"
        f"  Итого: <b>{total:.2f} руб.</b>"
    )


async def add_expense_general(purpose: str, total_amount: float) -> str:
    """Общеклассовая трата — делится поровну."""
    return await split_expense(purpose, total_amount)


async def clear_student_contribution(student_query: str, purpose: str) -> str:
    """Обнуляет взнос конкретного ученика по назначению."""
    name, _, ambiguous = await resolve_student(student_query)
    if ambiguous:
        return "Уточните:\n" + "\n".join(f"• {esc(n)}" for n in ambiguous)
    if name is None:
        return f"Ученик <b>«{esc(student_query)}»</b> не найден."

    # Ищем колонку по нечёткому совпадению с префиксом
    col_idx, col_name = await get_client().find_finance_column_fuzzy(purpose, prefix=CONTRIB_PREFIX)
    if col_name is None:
        return f"Столбец «{CONTRIB_PREFIX}{esc(purpose)}» не найден в «Финансы»."

    found = await get_client().update_finance_student_cell(name, col_name, "")
    if not found:
        return f"Строка ученика <b>{esc(name)}</b> не найдена в «Финансы»."

    display_purpose = col_name[len(CONTRIB_PREFIX):]
    log.info("Взнос очищен: %s / %s", name, col_name)
    return f"✅ Взнос <b>{esc(name)}</b> на «{esc(display_purpose)}» удалён."


# ── Поиск и удаление столбца ─────────────────────────────────────────────

async def find_column_by_purpose(
    purpose: str,
    prefix: str = "",
) -> tuple[int | None, str | None]:
    """Нечёткий поиск. Возвращает (1-based col_idx, actual_name) или (None, None)."""
    return await get_client().find_finance_column_fuzzy(purpose, prefix=prefix)


async def delete_finance_column(col_idx: int, purpose: str) -> str:
    await get_client().delete_finance_column(col_idx)
    return f"🗑 Столбец «{esc(purpose)}» удалён из «Финансы»."
