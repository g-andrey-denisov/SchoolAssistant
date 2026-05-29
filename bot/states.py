from aiogram.fsm.state import State, StatesGroup


class AddStudentForm(StatesGroup):
    """Пошаговый диалог добавления ученика."""
    full_name = State()
    birthday = State()
    parent_name = State()
    parent_phone = State()
    confirm = State()


class ConfirmAction(StatesGroup):
    """Ожидание подтверждения деструктивной операции."""
    waiting = State()


class ClarifyingState(StatesGroup):
    """Ожидание уточняющего ответа (бот задал вопрос, ждёт пропущенное поле)."""
    waiting = State()
