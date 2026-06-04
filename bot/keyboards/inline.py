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


# ── Сверка списков ───────────────────────────────────────────────────────────

def compare_remove_keyboard() -> InlineKeyboardMarkup:
    """Что сделать с учеником, которого нет в новом списке."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data="cmp_rm_delete"),
        InlineKeyboardButton(text="💤 Не ходит", callback_data="cmp_rm_inactive"),
    )
    builder.row(InlineKeyboardButton(text="↩️ Оставить", callback_data="cmp_rm_keep"))
    return builder.as_markup()


def compare_gender_keyboard() -> InlineKeyboardMarkup:
    """Выбор пола при добавлении в режиме сверки (+ пропустить)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👦 Мужской", callback_data="gender_male"),
        InlineKeyboardButton(text="👧 Женский", callback_data="gender_female"),
    )
    builder.row(InlineKeyboardButton(text="⏭ Пропустить", callback_data="cmp_add_skip"))
    return builder.as_markup()


def compare_skip_keyboard() -> InlineKeyboardMarkup:
    """Кнопка «пропустить» для текстовых шагов мастера сверки."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⏭ Пропустить", callback_data="cmp_add_skip"))
    return builder.as_markup()


def compare_confirm_keyboard() -> InlineKeyboardMarkup:
    """Финальное подтверждение добавления ученика при сверке."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Добавить", callback_data="cmp_add_yes"),
        InlineKeyboardButton(text="⏭ Пропустить", callback_data="cmp_add_no"),
    )
    return builder.as_markup()
