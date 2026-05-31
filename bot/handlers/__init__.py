from aiogram import Dispatcher

from .callbacks import router as callbacks_router
from .compare_lists import router as compare_lists_router
from .messages import router as messages_router
from .students_fsm import router as students_fsm_router
from .system import router as system_router
from .voice import router as voice_router


def register_all_handlers(dp: Dispatcher) -> None:
    # Порядок важен: system и FSM регистрируются раньше главного диспетчера.
    # compare_lists — до voice/messages, чтобы перехватывать триггер «Сравни списки».
    dp.include_router(system_router)
    dp.include_router(students_fsm_router)
    dp.include_router(callbacks_router)
    dp.include_router(compare_lists_router)
    dp.include_router(voice_router)
    dp.include_router(messages_router)
