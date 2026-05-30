"""Финансовые отчёты на основе листа «Финансы»."""

import logging
from collections import defaultdict

from sheets.client import _to_float, get_client
from sheets.schema import CONTRIB_PREFIX, EXPENSE_PREFIX, COL_STUDENT
from services.students import resolve_student
from utils.text import esc

log = logging.getLogger(__name__)


def _strip(col: str, prefix: str) -> str:
    """Убирает префикс из имени колонки для отображения."""
    return col[len(prefix):] if col.startswith(prefix) else col


async def _finance_matrix() -> tuple[list[str], list[str], list[tuple[int, dict]]]:
    """
    Возвращает (contrib_cols, expense_cols, rows).
    contrib_cols / expense_cols — полные имена колонок с префиксами.
    """
    headers, rows = await get_client().get_finance_data()
    purpose_headers = headers[1:]  # без «ФИО ученика»
    contrib_cols = [h for h in purpose_headers if h.startswith(CONTRIB_PREFIX)]
    expense_cols = [h for h in purpose_headers if h.startswith(EXPENSE_PREFIX)]
    return contrib_cols, expense_cols, rows


async def get_balance() -> dict:
    """Возвращает {contributions, expenses, balance}."""
    contrib_cols, expense_cols, rows = await _finance_matrix()
    contributions = sum(
        _to_float(row.get(col, ""))
        for col in contrib_cols
        for _, row in rows
    )
    expenses = sum(
        _to_float(row.get(col, ""))
        for col in expense_cols
        for _, row in rows
    )
    return {"contributions": contributions, "expenses": expenses, "balance": contributions - expenses}


async def report_balance() -> str:
    b = await get_balance()
    emoji = "🟢" if b["balance"] >= 0 else "🔴"
    return (
        f"💰 <b>Состояние фонда</b>\n"
        f"  Взносы:  <b>{b['contributions']:.2f} руб.</b>\n"
        f"  Траты:   <b>{b['expenses']:.2f} руб.</b>\n"
        f"  {emoji} Остаток: <b>{b['balance']:.2f} руб.</b>"
    )


async def report_contributions_total() -> str:
    b = await get_balance()
    return f"💵 Общая сумма взносов: <b>{b['contributions']:.2f} руб.</b>"


async def report_expenses_total() -> str:
    b = await get_balance()
    return f"💸 Общая сумма трат: <b>{b['expenses']:.2f} руб.</b>"


async def report_contributions_by_student() -> str:
    """
    Детальный отчёт: кто сдал (с суммами по назначениям) и кто ничего не сдал.
    Включает только активных учеников.
    """
    from services.students import get_active_students

    contrib_cols, _, rows = await _finance_matrix()
    active = await get_active_students()
    active_names = {s[COL_STUDENT] for s in active}

    # Собираем данные из «Финансы» по активным ученикам
    finance_map: dict[str, dict[str, float]] = {}
    for _, row in rows:
        name = row.get(COL_STUDENT, "").strip()
        if name not in active_names:
            continue
        by_purpose = {
            _strip(col, CONTRIB_PREFIX): _to_float(row.get(col, ""))
            for col in contrib_cols
            if _to_float(row.get(col, "")) > 0
        }
        finance_map[name] = by_purpose

    paid: list[tuple[str, float, dict]] = []
    not_paid: list[str] = []

    for name in active_names:
        by_purpose = finance_map.get(name, {})
        total = sum(by_purpose.values())
        if total > 0:
            paid.append((name, total, by_purpose))
        else:
            not_paid.append(name)

    paid.sort(key=lambda x: x[0])
    not_paid.sort()

    lines = ["💵 <b>Взносы по ученикам</b>"]

    if paid:
        lines.append(f"\n✅ Сдавали ({len(paid)} чел.):")
        for name, total, _ in paid:
            lines.append(f"  • <b>{esc(name)}</b> — {total:.0f} руб.")
    else:
        lines.append("\nВзносов пока нет.")

    if not_paid:
        lines.append(f"\n❌ Не сдавали ({len(not_paid)} чел.):")
        for name in not_paid:
            lines.append(f"  • {esc(name)}")

    grand = sum(t for _, t, _ in paid)
    lines.append(f"\n<b>Всего взносов: {grand:.2f} руб.</b>")
    return "\n".join(lines)


async def report_contributions_list() -> str:
    contrib_cols, _, rows = await _finance_matrix()
    if not contrib_cols:
        return "Взносов пока нет."
    items = [
        (_strip(col, CONTRIB_PREFIX), sum(_to_float(row.get(col, "")) for _, row in rows))
        for col in contrib_cols
    ]
    items = [(name, total) for name, total in items if total > 0]
    if not items:
        return "Взносов пока нет."
    lines = [f"  • {esc(name)}: <b>{total:.2f} руб.</b>" for name, total in items]
    grand = sum(t for _, t in items)
    return "💵 <b>Взносы:</b>\n" + "\n".join(lines) + f"\n\n<b>Итого: {grand:.2f} руб.</b>"


async def report_expenses_list() -> str:
    _, expense_cols, rows = await _finance_matrix()
    if not expense_cols:
        return "Трат пока нет."
    items = [
        (_strip(col, EXPENSE_PREFIX), sum(_to_float(row.get(col, "")) for _, row in rows))
        for col in expense_cols
    ]
    items = [(name, total) for name, total in items if total > 0]
    if not items:
        return "Трат пока нет."
    lines = [f"  • {esc(name)}: <b>{total:.2f} руб.</b>" for name, total in items]
    grand = sum(t for _, t in items)
    return "💸 <b>Траты:</b>\n" + "\n".join(lines) + f"\n\n<b>Итого: {grand:.2f} руб.</b>"


async def report_full() -> str:
    b = await get_balance()
    c_list = await report_contributions_list()
    e_list = await report_expenses_list()
    emoji = "🟢" if b["balance"] >= 0 else "🔴"
    return (
        f"📊 <b>Финансовый отчёт</b>\n\n"
        f"{c_list}\n\n{e_list}\n\n"
        f"{emoji} <b>Остаток в кассе: {b['balance']:.2f} руб.</b>"
    )


async def report_class_finance() -> str:
    """Финансовый отчёт по каждому активному ученику: взносы, траты, баланс."""
    from services.students import get_active_students

    contrib_cols, expense_cols, rows = await _finance_matrix()
    active = await get_active_students()
    active_names_ordered = [s[COL_STUDENT] for s in active]  # порядок из листа Контакты

    finance_map = {row.get(COL_STUDENT, ""): row for _, row in rows}

    lines = [f"📊 <b>Финансовый отчёт класса</b> ({len(active_names_ordered)} чел.)\n"]

    total_c = total_e = 0.0
    for name in sorted(active_names_ordered):
        row = finance_map.get(name, {})
        c = sum(_to_float(row.get(col, "")) for col in contrib_cols)
        e = sum(_to_float(row.get(col, "")) for col in expense_cols)
        bal = c - e
        total_c += c
        total_e += e
        sign = "+" if bal >= 0 else ""
        lines.append(
            f"  <b>{esc(name)}</b>\n"
            f"    взносы: {c:.0f} / траты: {e:.0f} / баланс: {sign}{bal:.0f} руб."
        )

    total_bal = total_c - total_e
    sign = "+" if total_bal >= 0 else ""
    lines.append(
        f"\n<b>Итого по классу:</b>\n"
        f"  Взносы: {total_c:.2f} руб.\n"
        f"  Траты:  {total_e:.2f} руб.\n"
        f"  Остаток: {sign}{total_bal:.2f} руб."
    )
    return "\n".join(lines)


async def report_student(query: str) -> str:
    name, _, ambiguous = await resolve_student(query)
    if ambiguous:
        return "Уточните:\n" + "\n".join(f"• {esc(n)}" for n in ambiguous)
    if name is None:
        return f"Ученик <b>«{esc(query)}»</b> не найден."

    contrib_cols, expense_cols, rows = await _finance_matrix()
    student_row = next((row for _, row in rows if row.get(COL_STUDENT) == name), None)
    if student_row is None:
        return f"Данные по <b>{esc(name)}</b> отсутствуют в «Финансы»."

    contributions = 0.0
    expenses = 0.0
    details = []
    for col in contrib_cols:
        v = _to_float(student_row.get(col, ""))
        if v:
            contributions += v
            details.append(f"  💵 {esc(_strip(col, CONTRIB_PREFIX))}: +{v:.2f}")
    for col in expense_cols:
        v = _to_float(student_row.get(col, ""))
        if v:
            expenses += v
            details.append(f"  💸 {esc(_strip(col, EXPENSE_PREFIX))}: {v:.2f}")

    balance = contributions - expenses
    emoji = "🟢" if balance >= 0 else "🔴"
    detail_str = "\n".join(details) if details else "  (нет данных)"
    return (
        f"👤 <b>Отчёт по {esc(name)}:</b>\n{detail_str}\n\n"
        f"  Взносы: <b>{contributions:.2f} руб.</b>\n"
        f"  Траты:  <b>{expenses:.2f} руб.</b>\n"
        f"  {emoji} Баланс: <b>{balance:.2f} руб.</b>"
    )


async def report_paid(purpose: str | None, paid: bool) -> str:
    from services.students import get_active_students

    active_students = await get_active_students()
    all_names = {s[COL_STUDENT] for s in active_students}

    if purpose:
        # Ищем колонку «Взнос: <purpose>»
        col_idx, col_name = await get_client().find_finance_column_fuzzy(purpose, prefix=CONTRIB_PREFIX)
        if col_name:
            col_values = await get_client().get_finance_column_values(col_name)
        else:
            col_values = {}
            col_name = purpose

        if paid:
            names = sorted(n for n, v in col_values.items() if v > 0 and n in all_names)
            header = f"✅ Сдали на «{esc(_strip(col_name, CONTRIB_PREFIX))}» ({len(names)} чел.):"
        else:
            names = sorted(n for n in all_names if col_values.get(n, 0) <= 0)
            header = f"❌ Не сдали на «{esc(_strip(col_name, CONTRIB_PREFIX))}» ({len(names)} чел.):"
    else:
        # Без конкретного назначения: проверяем любой взнос
        contrib_cols, _, rows = await _finance_matrix()
        has_contribution = {
            row.get(COL_STUDENT, "")
            for _, row in rows
            if any(_to_float(row.get(c, "")) > 0 for c in contrib_cols)
        }
        if paid:
            names = sorted(has_contribution & all_names)
            header = f"✅ Сдавали взносы ({len(names)} чел.):"
        else:
            names = sorted(all_names - has_contribution)
            header = f"❌ Не сдавали взносов ({len(names)} чел.):"

    if not names:
        return header + "\nСписок пуст."
    return header + "\n" + "\n".join(f"  • {esc(n)}" for n in names)
