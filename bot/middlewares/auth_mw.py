"""Middleware авторизации: пропускает только пользователей из whitelist.

Если settings.allowed_user_ids пуст — НИКТО не пропускается (бот закрыт).
"""

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import settings

log = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        allowed = settings.allowed_user_ids
        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)

        # Пусто = бот закрыт для всех. Иначе — только id из whitelist.
        if allowed and user_id in allowed:
            return await handler(event, data)

        if not allowed:
            log.warning("ALLOWED_USER_IDS пуст — бот закрыт. Отказано user=%s", user_id)
        else:
            log.warning("Доступ запрещён: user=%s (%s)", user_id, type(event).__name__)
        if isinstance(event, Message):
            await event.answer("⛔ Доступ запрещён.")
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔ Доступ запрещён.", show_alert=True)
        return None
