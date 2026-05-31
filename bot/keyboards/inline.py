from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def confirm_keyboard(yes_text: str = "Да ✅", no_text: str = "Отменить ❌") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=yes_text, callback_data="confirm_yes"),
        InlineKeyboardButton(text=no_text, callback_data="confirm_no"),
    )
    return builder.as_markup()


def gender_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👦 Мужской", callback_data="gender_male"),
        InlineKeyboardButton(text="👧 Женский", callback_data="gender_female"),
    )
    return builder.as_markup()
