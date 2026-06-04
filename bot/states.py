from aiogram.fsm.state import State, StatesGroup


class AddStudentForm(StatesGroup):
    """Пошаговый диалог добавления ученика."""
    full_name = State()
    gender = State()
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


class CompareListsForm(StatesGroup):
    """
    Сверка внешнего списка с БД.
    Очереди на удаление/добавление и прогресс мастера хранятся в FSM-data.
    """
    removing = State()  # подтверждение по каждому «лишнему» в БД ученику
    adding = State()    # пошаговый сбор полей нового ученика (поле — в add_step)
    confirm = State()   # финальное подтверждение добавления ученика
