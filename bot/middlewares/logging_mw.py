"""Middleware: логирует каждый входящий update с user_id и типом."""

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

log = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        start = time.monotonic()

        user = getattr(getattr(event, "from_user", None), "id", "?")
        update_type = type(event).__name__

        try:
            result = await handler(event, data)
            elapsed = (time.monotonic() - start) * 1000
            log.debug("[%s] user=%s %.1f ms", update_type, user, elapsed)
            return result
        except Exception:
            elapsed = (time.monotonic() - start) * 1000
            log.exception("[%s] user=%s FAILED %.1f ms", update_type, user, elapsed)
            raise
