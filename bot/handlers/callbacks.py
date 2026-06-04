"""
Обработчики inline-кнопок подтверждения/отмены.
Обслуживает два сценария:
  1. AddStudentForm.confirm — финальный шаг добавления ученика
  2. ConfirmAction.waiting — любая деструктивная операция
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.states import AddStudentForm, ConfirmAction
from services import finance as finance_svc
from services import students as students_svc

log = logging.getLogger(__name__)
router = Router(name="callbacks")


async def _edit_and_clear(callback: CallbackQuery, state: FSMContext) -> tuple[dict, str | None]:
    """Убирает клавиатуру с сообщения, очищает состояние, возвращает данные."""
    data = await state.get_data()
    current_state = await state.get_state()
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()
    return data, current_state


@router.callback_query(F.data == "confirm_yes")
async def on_confirm_yes(callback: CallbackQuery, state: FSMContext) -> None:
    data, current_state = await _edit_and_clear(callback, state)

    # ── Добавление ученика ────────────────────────────────────────────────
    if current_state == AddStudentForm.confirm.state:
        result = await students_svc.add_student(data)
        await callback.message.answer(result)
        return

    # ── Деструктивная операция ────────────────────────────────────────────
    if current_state == ConfirmAction.waiting.state:
        action = data.get("action")

        if action == "delete_student":
            result = await students_svc.delete_student(
                data["student_name"], data["row_num"]
            )
            await callback.message.answer(result)

        elif action == "mark_inactive":
            result = await students_svc.mark_inactive(
                data["student_name"], data["row_num"]
            )
            await callback.message.answer(result)

        elif action == "delete_finance_column":
            result = await finance_svc.delete_finance_column(
                data["col_idx"], data["purpose"]
            )
            await callback.message.answer(result)

        else:
            log.warning("Неизвестное pending action: %s", action)
            await callback.message.answer("⚠️ Неизвестное действие.")
        return

    log.warning("confirm_yes вне ожидаемого состояния: %s", current_state)
    await callback.message.answer("⚠️ Нет активного действия для подтверждения.")


@router.callback_query(F.data == "confirm_no")
async def on_confirm_no(callback: CallbackQuery, state: FSMContext) -> None:
    await _edit_and_clear(callback, state)
    await callback.message.answer("❌ Отменено.")
