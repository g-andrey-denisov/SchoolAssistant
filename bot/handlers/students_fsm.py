"""FSM-диалог добавления нового ученика."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import confirm_keyboard, gender_keyboard
from bot.states import AddStudentForm
from sheets.schema import (
    COL_BIRTHDAY, COL_GENDER, COL_NOTE, COL_PARENT_NAME, COL_PARENT_PHONE,
    COL_STUDENT as COL_NAME, GENDER_FEMALE, GENDER_MALE, parse_gender,
)
from utils.dates import parse_date
from utils.text import esc

log = logging.getLogger(__name__)
router = Router(name="students_fsm")

_SKIP = {"пропустить", "пропуск", "-", "."}


def _is_skip(text: str) -> bool:
    return text.strip().lower() in _SKIP


def _gender_label(value: str) -> str:
    g = parse_gender(value)
    if g == GENDER_MALE:
        return "мужской"
    if g == GENDER_FEMALE:
        return "женский"
    return "не указан"


def _student_summary(data: dict) -> str:
    lines = [
        f"👤 ФИО: <b>{esc(data.get(COL_NAME, '—'))}</b>",
        f"⚧ Пол: <b>{_gender_label(data.get(COL_GENDER, ''))}</b>",
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
    await state.set_state(AddStudentForm.gender)
    await message.answer(
        f"✅ ФИО: <b>{esc(name)}</b>\n\n"
        "Укажите пол ученика:",
        reply_markup=gender_keyboard(),
    )


async def _save_gender(message: Message, state: FSMContext, gender: str) -> None:
    """Сохраняет пол и переходит к вводу дня рождения."""
    await state.update_data({COL_GENDER: gender})
    await state.set_state(AddStudentForm.birthday)
    await message.answer(
        f"✅ Пол: <b>{_gender_label(gender)}</b>\n\n"
        "Введите день рождения (ДД.ММ.ГГГГ) или «пропустить»:"
    )


@router.callback_query(AddStudentForm.gender, F.data.in_({"gender_male", "gender_female"}))
async def got_gender_cb(callback: CallbackQuery, state: FSMContext) -> None:
    gender = GENDER_MALE if callback.data == "gender_male" else GENDER_FEMALE
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()
    await _save_gender(callback.message, state, gender)


@router.message(AddStudentForm.gender)
async def got_gender_text(message: Message, state: FSMContext) -> None:
    gender = parse_gender(message.text)
    if gender is None:
        await message.answer(
            "Не понял. Выберите пол кнопкой или напишите «м» / «ж»:",
            reply_markup=gender_keyboard(),
        )
        return
    await _save_gender(message, state, gender)


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
