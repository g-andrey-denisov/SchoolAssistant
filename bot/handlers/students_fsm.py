"""FSM-диалог добавления нового ученика."""

import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.inline import confirm_keyboard
from bot.states import AddStudentForm
from sheets.schema import COL_BIRTHDAY, COL_NOTE, COL_PARENT_NAME, COL_PARENT_PHONE, COL_STUDENT as COL_NAME
from utils.dates import parse_date
from utils.text import esc

log = logging.getLogger(__name__)
router = Router(name="students_fsm")

_SKIP = {"пропустить", "пропуск", "-", "."}


def _is_skip(text: str) -> bool:
    return text.strip().lower() in _SKIP


def _student_summary(data: dict) -> str:
    lines = [
        f"👤 ФИО: <b>{esc(data.get(COL_NAME, '—'))}</b>",
        f"🎂 День рождения: <b>{esc(data.get(COL_BIRTHDAY, '—') or '—')}</b>",
        f"👨‍👩‍👧 ФИО родителя: <b>{esc(data.get(COL_PARENT_NAME, '—') or '—')}</b>",
        f"📞 Телефон: <b>{esc(data.get(COL_PARENT_PHONE, '—') or '—')}</b>",
    ]
    note = data.get(COL_NOTE, "")
    if note:
        lines.append(f"📝 Примечание: <b>{esc(note)}</b>")
    return "\n".join(lines)


@router.message(AddStudentForm.full_name)
async def got_full_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name or _is_skip(name):
        await message.answer("ФИО обязательно. Введите полное имя ученика:")
        return
    await state.update_data({COL_NAME: name})
    await state.set_state(AddStudentForm.birthday)
    await message.answer(
        f"✅ ФИО: <b>{esc(name)}</b>\n\n"
        "Введите день рождения (ДД.ММ.ГГГГ) или «пропустить»:"
    )


@router.message(AddStudentForm.birthday)
async def got_birthday(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""
    if _is_skip(text):
        birthday = ""
    else:
        bday = parse_date(text)
        if bday is None:
            await message.answer(
                "Не удалось распознать дату. Введите в формате ДД.ММ.ГГГГ или «пропустить»:"
            )
            return
        birthday = text

    await state.update_data({COL_BIRTHDAY: birthday})
    await state.set_state(AddStudentForm.parent_name)
    await message.answer("Введите ФИО родителя или «пропустить»:")


@router.message(AddStudentForm.parent_name)
async def got_parent_name(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""
    parent_name = "" if _is_skip(text) else text
    await state.update_data({COL_PARENT_NAME: parent_name})
    await state.set_state(AddStudentForm.parent_phone)
    await message.answer("Введите телефон родителя или «пропустить»:")


@router.message(AddStudentForm.parent_phone)
async def got_parent_phone(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""
    parent_phone = "" if _is_skip(text) else text
    await state.update_data({COL_PARENT_PHONE: parent_phone})

    data = await state.get_data()
    await state.set_state(AddStudentForm.confirm)
    await message.answer(
        "Проверьте данные:\n\n" + _student_summary(data) + "\n\nДобавить ученика?",
        reply_markup=confirm_keyboard(),
    )
