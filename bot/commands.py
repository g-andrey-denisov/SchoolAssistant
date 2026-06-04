"""Регистрация команд и описаний бота в Telegram.

Команды (set_my_commands) одновременно дают выпадающий список при вводе «/».
Описания (set_my_description / set_my_short_description) видны в карточке бота
и на экране до нажатия /start.
"""

import logging

from aiogram import Bot
from aiogram.types import BotCommand

log = logging.getLogger(__name__)

# Список команд для меню «/». Каждая имеет реальный обработчик
# (см. bot/handlers/system.py и messages.py).
BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Начать работу"),
    BotCommand(command="help", description="Что я умею"),
    BotCommand(command="balance", description="Баланс класса"),
    BotCommand(command="report", description="Финансовый отчёт класса"),
    BotCommand(command="birthdays", description="Ближайшие дни рождения"),
    BotCommand(command="reset", description="Сбросить текущий диалог"),
]

# До 120 символов.
SHORT_DESCRIPTION = (
    "Помощник родительского комитета: ученики, взносы и траты, "
    "отчёты, контакты, дни рождения. Можно голосом."
)

# До 512 символов. Plain-text (Telegram не рендерит разметку здесь).
DESCRIPTION = (
    "Веду дела класса прямо в Telegram — пишите или говорите своими словами.\n"
    "\n"
    "• Ученики: добавить, отметить выбывших, посчитать\n"
    "• Финансы: взносы, траты, баланс\n"
    "• Отчёты: кто сдал / не сдал, итоги по классу\n"
    "• Контакты и телефоны родителей\n"
    "• Дни рождения и напоминания\n"
    "\n"
    "Данные — в вашей Google-таблице. Поддерживаются голосовые сообщения."
)


async def setup_bot_profile(bot: Bot) -> None:
    """Применяет команды и описания к боту. Вызывать один раз при старте."""
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_my_short_description(SHORT_DESCRIPTION)
    await bot.set_my_description(DESCRIPTION)
    log.info("Команды (%d) и описания бота обновлены", len(BOT_COMMANDS))
