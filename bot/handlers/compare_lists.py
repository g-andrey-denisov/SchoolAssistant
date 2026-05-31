"""
Сверка списков учеников: команда «Сравни списки».

Триггеры (в состоянии default_state):
  • текст, начинающийся со «Сравни списки …», а ниже — ученики по строкам;
  • документ (.txt/.csv/.xlsx) с подписью «Сравни списки».

Сценарий:
  1. Парсим внешний список (services.roster) и сравниваем с БД.
  2. Показываем расхождения.
  3. По каждому «лишнему» в БД ученику спрашиваем: удалить / «не ходит» / оставить.
  4. Каждого нового ученика добавляем пошаговым мастером (поля можно пропускать,
     уже известные из списка — подставляются), с финальным подтверждением.
"""

import logging
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import (
    compare_confirm_keyboard, compare_gender_keyboard, compare_remove_keyboard,
    compare_skip_keyboard,
)
from bot.states import CompareListsForm
from services import roster as roster_svc
from services import students as students_svc
from sheets.schema import (
    COL_BIRTHDAY, COL_GENDER, COL_PARENT_NAME, COL_PARENT_PHONE, COL_STUDENT,
    GENDER_FEMALE, GENDER_MALE,
)
from utils.dates import parse_date
from utils.text import esc

from .students_fsm import _student_summary

log = logging.getLogger(__name__)
router = Router(name="compare_lists")

# «Сравни списки», «сравни список», «сравни списки учеников»
TRIGGER = re.compile(r"(?is)^\s*сравни\s+списк")

# Порядок и подписи полей, которые добираем мастером для нового ученика.
_ADD_FIELDS = [COL_GENDER, COL_BIRTHDAY, COL_PARENT_NAME, COL_PARENT_PHONE]
_FIELD_PROMPTS = {
    COL_BIRTHDAY: "Введите день рождения (ДД.ММ.ГГГГ) или «пропустить»:",
    COL_PARENT_NAME: "Введите ФИО родителя или «пропустить»:",
    COL_PARENT_PHONE: "Введите телефон родителя или «пропустить»:",
}

_MAX_LIST = 40  # сколько имён максимум показывать в сводке расхождений


# ── Фильтры-триггеры ─────────────────────────────────────────────────────────

def _text_trigger(message: Message) -> bool:
    return bool(message.text and TRIGGER.match(message.text))


def _doc_trigger(message: Message) -> bool:
    return bool(message.document and message.caption and TRIGGER.match(message.caption))


# ── Точки входа ──────────────────────────────────────────────────────────────

@router.message(StateFilter(default_state), _text_trigger)
async def on_text(message: Message, state: FSMContext) -> None:
    # Первая строка — сама команда, остальное — список учеников.
    lines = message.text.splitlines()
    roster = roster_svc.parse_text_lines("\n".join(lines[1:]))
    if not roster:
        await message.answer(
            "Пришлите список для сверки одним из способов:\n"
            "• приложите файл <b>.xlsx</b>, <b>.csv</b> или <b>.txt</b> с подписью «Сравни списки»;\n"
            "• или вставьте список прямо в сообщение после команды — по одному ученику в строке."
        )
        return
    await _start(message, state, roster)


@router.message(StateFilter(default_state), _doc_trigger)
async def on_document(message: Message, state: FSMContext) -> None:
    doc = message.document
    thinking = await message.answer("📥 Читаю файл…")
    try:
        tg_file = await message.bot.get_file(doc.file_id)
        buf = await message.bot.download_file(tg_file.file_path)
        data = buf.read()
    except Exception as exc:
        log.error("Сверка: ошибка загрузки файла: %s", exc)
        await thinking.edit_text("⚠️ Не удалось загрузить файл.")
        return

    try:
        roster = roster_svc.parse_roster(doc.file_name or "", data)
    except ValueError as exc:
        await thinking.edit_text(f"⚠️ {esc(exc)}")
        return
    except Exception as exc:
        log.exception("Сверка: ошибка парсинга файла: %s", exc)
        await thinking.edit_text("⚠️ Не удалось разобрать файл. Проверьте формат.")
        return

    await thinking.delete()
    if not roster:
        await message.answer("В файле не найдено ни одного ученика.")
        return
    await _start(message, state, roster)


# ── Запуск сверки ────────────────────────────────────────────────────────────

def _summary_text(comp: roster_svc.Comparison) -> str:
    lines = [
        "📊 <b>Сравнение списков</b>",
        f"В новом списке: <b>{comp.new_total}</b> · в БД: <b>{comp.db_total}</b> · "
        f"совпало: <b>{len(comp.matched)}</b>",
    ]

    def _bullets(names: list[str]) -> str:
        shown = names[:_MAX_LIST]
        out = "\n".join(f"• {esc(n)}" for n in shown)
        if len(names) > _MAX_LIST:
            out += f"\n… и ещё {len(names) - _MAX_LIST}"
        return out

    if comp.to_add:
        names = [e.get(COL_STUDENT, "") for e in comp.to_add]
        lines.append(f"\n➕ <b>Добавить ({len(names)})</b> — нет в БД:\n{_bullets(names)}")
    if comp.to_remove:
        names = [n for _, n in comp.to_remove]
        lines.append(
            f"\n🗑 <b>Удалить/пометить ({len(names)})</b> — нет в новом списке:\n{_bullets(names)}"
        )
    if not comp.to_add and not comp.to_remove:
        lines.append("\n✅ Списки совпадают, расхождений нет.")
    return "\n".join(lines)


async def _start(message: Message, state: FSMContext, roster: list[dict]) -> None:
    db_indexed = await students_svc.get_students_indexed()
    comp = roster_svc.compare(roster, db_indexed)

    await message.answer(_summary_text(comp))
    if not comp.to_add and not comp.to_remove:
        return

    await state.set_state(CompareListsForm.removing)
    await state.update_data(
        remove_queue=[{"name": name, "row_num": rn} for rn, name in comp.to_remove],
        add_queue=comp.to_add,
        added_count=0,
        removed_count=0,
    )
    await _next_step(message, state)


# ── Маршрутизация шагов ──────────────────────────────────────────────────────

async def _next_step(message: Message, state: FSMContext) -> None:
    """Переходит к следующему действию: удаление → добавление → завершение."""
    data = await state.get_data()
    if data.get("remove_queue"):
        head = data["remove_queue"][0]
        await state.set_state(CompareListsForm.removing)
        await message.answer(
            f"🗑 <b>{esc(head['name'])}</b> есть в БД, но отсутствует в новом списке.\n"
            "Что сделать?",
            reply_markup=compare_remove_keyboard(),
        )
        return
    if data.get("add_queue"):
        await _begin_addition(message, state)
        return
    await _finish(message, state)


async def _finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    added = data.get("added_count", 0)
    removed = data.get("removed_count", 0)
    await state.clear()
    await message.answer(
        "✅ <b>Сверка завершена.</b>\n"
        f"➕ Добавлено: <b>{added}</b>\n"
        f"🗑 Удалено/помечено: <b>{removed}</b>"
    )


# ── Фаза удаления ────────────────────────────────────────────────────────────

async def _handle_removal(callback: CallbackQuery, state: FSMContext, mode: str) -> None:
    data = await state.get_data()
    queue = data.get("remove_queue", [])
    if not queue:
        await callback.answer()
        await _next_step(callback.message, state)
        return

    head, rest = queue[0], queue[1:]
    name = head["name"]
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()

    removed = data.get("removed_count", 0)
    if mode == "keep":
        result = f"↩️ <b>{esc(name)}</b> оставлен без изменений."
    else:
        # Перерешаем строку по имени: после delete номера строк сдвигаются.
        resolved, row_num, _ = await students_svc.resolve_student(name)
        if row_num is None:
            result = f"⚠️ <b>{esc(name)}</b> не найден в БД (возможно, уже удалён)."
        elif mode == "delete":
            result = await students_svc.delete_student(resolved, row_num)
            removed += 1
        else:  # inactive
            result = await students_svc.mark_inactive(resolved, row_num)
            removed += 1

    await state.update_data(remove_queue=rest, removed_count=removed)
    await callback.message.answer(result)
    await _next_step(callback.message, state)


@router.callback_query(CompareListsForm.removing, F.data == "cmp_rm_delete")
async def rm_delete(callback: CallbackQuery, state: FSMContext) -> None:
    await _handle_removal(callback, state, "delete")


@router.callback_query(CompareListsForm.removing, F.data == "cmp_rm_inactive")
async def rm_inactive(callback: CallbackQuery, state: FSMContext) -> None:
    await _handle_removal(callback, state, "inactive")


@router.callback_query(CompareListsForm.removing, F.data == "cmp_rm_keep")
async def rm_keep(callback: CallbackQuery, state: FSMContext) -> None:
    await _handle_removal(callback, state, "keep")


# ── Фаза добавления (мастер) ─────────────────────────────────────────────────

async def _begin_addition(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    current = dict(data["add_queue"][0])  # копия: COL_STUDENT (+ поля из списка)
    await state.update_data(current=current, add_step=0)
    await message.answer(f"➕ <b>Новый ученик:</b> {esc(current.get(COL_STUDENT, '—'))}")
    await _ask_next_add_field(message, state)


async def _ask_next_add_field(message: Message, state: FSMContext) -> None:
    """Спрашивает первое незаполненное поле; что есть из списка — пропускает."""
    data = await state.get_data()
    current = data["current"]
    step = data.get("add_step", 0)

    while step < len(_ADD_FIELDS) and current.get(_ADD_FIELDS[step]):
        step += 1  # значение уже пришло из списка — не переспрашиваем

    if step >= len(_ADD_FIELDS):
        await state.update_data(add_step=step)
        await _show_add_confirm(message, state)
        return

    field = _ADD_FIELDS[step]
    await state.update_data(add_step=step)
    await state.set_state(CompareListsForm.adding)
    if field == COL_GENDER:
        await message.answer("Укажите пол ученика:", reply_markup=compare_gender_keyboard())
    else:
        await message.answer(_FIELD_PROMPTS[field], reply_markup=compare_skip_keyboard())


async def _advance_add(message: Message, state: FSMContext, value: str) -> None:
    """Сохраняет значение текущего поля и переходит к следующему."""
    data = await state.get_data()
    current = data["current"]
    step = data.get("add_step", 0)
    current[_ADD_FIELDS[step]] = value
    await state.update_data(current=current, add_step=step + 1)
    await _ask_next_add_field(message, state)


@router.callback_query(CompareListsForm.adding, F.data.in_({"gender_male", "gender_female"}))
async def add_gender_cb(callback: CallbackQuery, state: FSMContext) -> None:
    gender = GENDER_MALE if callback.data == "gender_male" else GENDER_FEMALE
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()
    await _advance_add(callback.message, state, gender)


@router.callback_query(CompareListsForm.adding, F.data == "cmp_add_skip")
async def add_skip_cb(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("Пропущено")
    await _advance_add(callback.message, state, "")


@router.message(CompareListsForm.adding)
async def add_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    step = data.get("add_step", 0)
    field = _ADD_FIELDS[step]
    text = (message.text or "").strip()
    if not text:
        return

    if field == COL_GENDER:
        from sheets.schema import parse_gender
        gender = parse_gender(text)
        if gender is None:
            await message.answer(
                "Не понял пол. Выберите кнопкой или напишите «м» / «ж»:",
                reply_markup=compare_gender_keyboard(),
            )
            return
        await _advance_add(message, state, gender)
        return

    if field == COL_BIRTHDAY and parse_date(text) is None:
        await message.answer(
            "Не удалось распознать дату. Введите в формате ДД.ММ.ГГГГ или «пропустить»:",
            reply_markup=compare_skip_keyboard(),
        )
        return

    await _advance_add(message, state, text)


async def _show_add_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(CompareListsForm.confirm)
    await message.answer(
        "Проверьте данные нового ученика:\n\n" + _student_summary(data["current"]),
        reply_markup=compare_confirm_keyboard(),
    )


@router.callback_query(CompareListsForm.confirm, F.data == "cmp_add_yes")
async def add_confirm_yes(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()
    result = await students_svc.add_student(data["current"])
    await callback.message.answer(result)
    await _pop_addition(state, added=True)
    await _next_step(callback.message, state)


@router.callback_query(CompareListsForm.confirm, F.data == "cmp_add_no")
async def add_confirm_no(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    name = data["current"].get(COL_STUDENT, "—")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()
    await callback.message.answer(f"⏭ <b>{esc(name)}</b> пропущен.")
    await _pop_addition(state, added=False)
    await _next_step(callback.message, state)


async def _pop_addition(state: FSMContext, added: bool) -> None:
    data = await state.get_data()
    queue = data.get("add_queue", [])[1:]
    update = {"add_queue": queue, "current": None, "add_step": 0}
    if added:
        update["added_count"] = data.get("added_count", 0) + 1
    await state.update_data(**update)
