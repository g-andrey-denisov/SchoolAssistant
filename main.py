"""
Точка входа бота. Запускать через run.py для авто-перезапуска при изменении файлов.
Прямой запуск: python main.py (без авто-перезапуска).
"""

import asyncio
import logging
import logging.handlers
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.commands import setup_bot_profile
from bot.handlers import register_all_handlers
from bot.middlewares.auth_mw import AuthMiddleware
from bot.middlewares.logging_mw import LoggingMiddleware
from config import settings


def setup_logging() -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    # Консоль
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    # Файл с ротацией по размеру (все уровни)
    size_handler = logging.handlers.RotatingFileHandler(
        filename=settings.log_dir / "app.log",
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    size_handler.setFormatter(fmt)
    root.addHandler(size_handler)

    # Отдельный файл только для ошибок, с ежедневной ротацией
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=settings.log_dir / "errors.log",
        when="midnight",
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    root.addHandler(error_handler)


async def main() -> None:
    setup_logging()
    log = logging.getLogger(__name__)
    log.info("Запуск SchoolAssistant бота (backend=%s)", settings.llm_backend)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    register_all_handlers(dp)

    await setup_bot_profile(bot)

    log.info("Начинаем polling…")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        log.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
