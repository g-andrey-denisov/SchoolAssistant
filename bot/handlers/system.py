"""Системные команды: /help, /reset, /cancel."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

log = logging.getLogger(__name__)
router = Router(name="system")

HELP_TEXT = """
📖 <b>Справка по командам</b>

<b>👩‍🎓 Ученики</b>
• «Новый ученик» — добавить (пошаговый диалог: ФИО, пол, ДР, родитель, телефон)
• «Сидоров не ходит» — пометить как неактивного (с подтверждением)
• «Ученик ушёл» / «Удали Иванова» — удалить из класса (с подтверждением)
• «Список класса» / «…с днями рождения» / «…с возрастом»
• «Сколько человек в классе»
• «Сколько мальчиков» / «Сколько девочек»
• «Сравни списки» — сверить класс с внешним списком (см. ниже)

<b>🔄 Сверка списков</b>
• «Сравни списки» + файл (.xlsx/.csv/.txt) или список в сообщении
• Бот покажет, кого добавить и кого удалить, и проведёт по шагам

<b>💰 Взносы</b>
• «Петров сдал 500 рублей на подарки» — взнос одного ученика
• «Весь класс сдал на полки по 120 рублей» — взнос всего класса
• «Егоров не сдал на Нужды класса» — убрать взнос ученика
• «Удали взнос Егорова на Нужды класса» — то же самое
• «Удали взнос на экскурсию у всех» — удалить столбец (с подтверждением)

<i>Взносы хранятся в столбцах «Взнос: Название»</i>

<b>💸 Траты</b>
• «Купили тетрадки на 8000» — трата на весь класс (делится поровну)
• «Раздели трату 5000 на подарки на всех» — явное деление
• «Распиши всем по 70 рублей на бумагу» — фиксированная сумма каждому
• «Удали трату на тетрадки у всех» — удалить столбец (с подтверждением)

<i>Траты хранятся в столбцах «Трата: Название»</i>

<b>📊 Отчёты</b>
• «Сколько осталось в кассе» / «…в фонде» — остаток (взносы − траты)
• «Сколько взносов» / «Сколько трат»
• «Покажи отчёт по финансам» — сводный отчёт
• «Кто сделал взносы» — список кто сдал и сколько, кто не сдал
• «Отчёт по взносам» — суммы по каждому назначению
• «Отчёт по тратам» — суммы по каждому назначению
• «Финансовый отчёт класса» — взносы/траты/баланс каждого ученика
• «Финансовый отчёт по Иванову» — отчёт по конкретному ученику
• «Кто сдал на экскурсию» / «Кто не сдал…»

<b>📞 Контакты</b>
• «Телефон Петрова» — ФИО родителя + номер телефона
• «Родители Денисова Артемия» — то же самое
• «Контакты Ивановой»

<b>🎂 Дни рождения</b>
• «У кого скоро день рождения» — ближайшие именинники
• «Список с днями рождения» / «…с возрастом»
• «Дни рождения по месяцам» — помесячная разбивка именинников

<b>⚙️ Системные</b>
• /help или «что ты умеешь» — эта справка
• /cancel или /reset — выйти из текущего диалога
• «Привет» / «Кто ты» — приветствие
""".strip()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


# ── Команды-ярлыки: строят интент напрямую, без вызова LLM ────────────────


@router.message(Command("balance"))
async def cmd_balance(message: Message, state: FSMContext) -> None:
    from bot.handlers.messages import _safe_dispatch
    from llm.intents import IntentAction, SheetIntent

    await _safe_dispatch(message, state, SheetIntent(action=IntentAction.REPORT_BALANCE))


@router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext) -> None:
    from bot.handlers.messages import _safe_dispatch
    from llm.intents import IntentAction, SheetIntent

    await _safe_dispatch(message, state, SheetIntent(action=IntentAction.REPORT_CLASS_FINANCE))


@router.message(Command("birthdays"))
async def cmd_birthdays(message: Message, state: FSMContext) -> None:
    from bot.handlers.messages import _safe_dispatch
    from llm.intents import IntentAction, SheetIntent

    await _safe_dispatch(message, state, SheetIntent(action=IntentAction.BIRTHDAY_UPCOMING))


@router.message(Command("reset", "cancel"))
async def cmd_reset(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("🔄 Диалог сброшен.")
    else:
        await message.answer("Нет активного диалога.")
    log.info("Контекст сброшен для user=%s", message.from_user.id)
