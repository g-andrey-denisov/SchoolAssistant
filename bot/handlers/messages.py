"""
Главный обработчик текстовых сообщений.
Получает интент от LLM и маршрутизирует к сервисам.
"""

import logging
import random
import re

from aiogram import Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import Message
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound

from bot.keyboards.inline import confirm_keyboard
from bot.states import AddStudentForm, ClarifyingState, ConfirmAction
from llm.client import parse_intent
from llm.intents import IntentAction, SheetIntent
from services import birthdays as bday_svc
from services import contacts as contacts_svc
from services import finance as finance_svc
from services import reports as reports_svc
from services import students as students_svc
from sheets.schema import CONTRIB_PREFIX, EXPENSE_PREFIX
from utils.text import esc

log = logging.getLogger(__name__)
router = Router(name="messages")

# ── Fast-path: ответы без вызова LLM ─────────────────────────────────────

_GREETINGS = frozenset({
    "привет", "здравствуй", "здравствуйте", "хай", "hi", "hello",
    "кто ты", "кто ты?", "что ты умеешь делать",
})
_TEST_WORDS = frozenset({"тест", "test"})
_TEST_RESPONSES = ["ок", "тест пройден", "ку-ку", "я здесь", "всё хорошо", "всё отлично"]

# Шаблоны запросов контактов, которые LLM иногда не распознаёт
_CONTACT_PATTERNS = re.compile(
    r"^(?:родители|контакты|телефон|номер|связь|позвонить)\s+(.+)$",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    """Нижний регистр, убираем знаки пунктуации по краям."""
    return re.sub(r"[^\w\s]", "", text.strip().lower()).strip()


# ── Поля, которые парсятся как число при уточнении ────────────────────────
_NUMERIC_FIELDS = {"amount", "per_student_amount"}


def _parse_amount(text: str) -> float | None:
    """Пробует извлечь число из строки (8000 / '8 000' / '8,5 тыс' → float)."""
    cleaned = re.sub(r"[^\d,.]", "", text.replace(" ", "").replace(" ", ""))
    if not cleaned:
        return None
    # Если есть и точка и запятая — убираем разделитель тысяч
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _try_fill_missing(intent: SheetIntent, field: str, text: str) -> bool:
    """
    Пробует заполнить пропущенное поле из текста ответа пользователя.
    Для числовых полей — парсит как float; для строковых — использует как есть.
    Возвращает True при успехе.
    """
    if field in _NUMERIC_FIELDS:
        val = _parse_amount(text)
        if val is None:
            return False
        setattr(intent, field, val)
        return True
    if field in ("purpose", "student_name", "note"):
        setattr(intent, field, text.strip())
        return True
    return False


async def _ask_clarification(
    message: Message,
    state: FSMContext,
    question: str,
    intent: SheetIntent,
    missing_field: str,
) -> None:
    """Сохраняет частичный интент в FSM и задаёт уточняющий вопрос."""
    await state.set_state(ClarifyingState.waiting)
    await state.update_data(
        partial_intent=intent.model_dump(),
        missing_field=missing_field,
    )
    await message.answer(f"❓ {question}")


async def _safe_dispatch(message: Message, state: FSMContext, intent: SheetIntent) -> None:
    """Вызывает _dispatch с единой обработкой ошибок Sheets."""
    try:
        await _dispatch(message, state, intent)
    except WorksheetNotFound as exc:
        log.error("Лист не найден: %s", exc)
        await message.answer(
            f"⚠️ Лист <b>«{esc(exc)}»</b> не найден в таблице.\n"
            "Проверьте настройку SHEET_* в .env или создайте лист вручную."
        )
    except (SpreadsheetNotFound, APIError) as exc:
        log.error("Ошибка Google Sheets API: %s", exc)
        await message.answer("⚠️ Ошибка доступа к Google Таблице. Проверьте права.")
    except Exception as exc:
        log.exception("Необработанная ошибка в _dispatch: %s", exc)
        await message.answer("⚠️ Внутренняя ошибка. Подробности в логах.")


# ── /start ────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я ассистент родительского комитета.\n\n"
        "Напишите, что нужно сделать, например:\n"
        "• <i>«Петров сдал 500 рублей на подарки»</i>\n"
        "• <i>«Кто не сдал на экскурсию?»</i>\n"
        "• <i>«Дай телефон Сидоровой»</i>\n\n"
        "Команда /help — полная справка."
    )


# ── Обработчик уточняющего ответа ────────────────────────────────────────

@router.message(StateFilter(ClarifyingState.waiting))
async def handle_clarification(message: Message, state: FSMContext) -> None:
    """Получает ответ на уточняющий вопрос, дополняет сохранённый интент и повторяет dispatch."""
    data = await state.get_data()
    text = (message.text or "").strip()
    if not text:
        return

    partial_dict = data.get("partial_intent", {})
    missing_field = data.get("missing_field", "")

    partial = SheetIntent.model_validate(partial_dict)

    if _try_fill_missing(partial, missing_field, text):
        # Поле заполнено — продолжаем обработку
        await state.clear()
        await _safe_dispatch(message, state, partial)
    else:
        # Ответ не похож на ожидаемое поле — обрабатываем как новый запрос
        await state.clear()
        thinking = await message.answer("⏳")
        try:
            new_intent = await parse_intent(text)
        except Exception as exc:
            log.exception("Ошибка parse_intent в clarification: %s", exc)
            await thinking.delete()
            await message.answer("⚠️ Не удалось разобрать запрос.")
            return
        await thinking.delete()
        log.info("Новый интент (из clarification): action=%s", new_intent.action)
        if new_intent.clarification_needed and new_intent.clarification_question:
            await message.answer(f"❓ {new_intent.clarification_question}")
            return
        await _safe_dispatch(message, state, new_intent)


# ── Главный обработчик (только когда нет активного FSM) ──────────────────

@router.message(StateFilter(default_state))
async def handle_text(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    if not text.strip():
        return

    # Fast-path: не тратим LLM-токены на стандартные фразы
    norm = _normalize(text)
    if norm in _GREETINGS:
        await cmd_start(message)
        return
    if norm in _TEST_WORDS:
        await message.answer(random.choice(_TEST_RESPONSES))
        return

    # Fast-path: контактные запросы вида «Родители Денисова Артемия»
    m = _CONTACT_PATTERNS.match(text.strip())
    if m:
        name_query = m.group(1).strip()
        result = await contacts_svc.get_phone(name_query)
        await message.answer(result)
        return

    thinking = await message.answer("⏳")
    try:
        intent = await parse_intent(text)
    except Exception as exc:
        log.exception("Ошибка parse_intent: %s", exc)
        await thinking.delete()
        await message.answer("⚠️ Не удалось разобрать запрос. Попробуйте ещё раз.")
        return

    await thinking.delete()
    log.info("Интент: action=%s | %s", intent.action, intent.raw_intent)

    if intent.clarification_needed and intent.clarification_question:
        await message.answer(f"❓ {intent.clarification_question}")
        return

    await _safe_dispatch(message, state, intent)


async def _dispatch(message: Message, state: FSMContext, intent: SheetIntent) -> None:
    action = intent.action

    # ── Ученики ───────────────────────────────────────────────────────────

    if action == IntentAction.STUDENT_ADD:
        await state.set_state(AddStudentForm.full_name)
        if intent.student_name:
            from bot.handlers.students_fsm import got_full_name
            fake = message.model_copy(update={"text": intent.student_name})
            await got_full_name(fake, state)
        else:
            await message.answer("Введите ФИО нового ученика:")
        return

    if action == IntentAction.STUDENT_MARK_INACTIVE:
        if not intent.student_name:
            await _ask_clarification(message, state, "Укажите ФИО ученика.", intent, "student_name")
            return
        name, row_num, ambiguous = await students_svc.resolve_student(intent.student_name)
        if ambiguous:
            await message.answer("Уточните:\n" + "\n".join(f"• {esc(n)}" for n in ambiguous))
            return
        if name is None:
            await message.answer(f"Ученик <b>«{esc(intent.student_name)}»</b> не найден.")
            return
        await state.set_state(ConfirmAction.waiting)
        await state.update_data(action="mark_inactive", student_name=name, row_num=row_num)
        await message.answer(f"Пометить <b>{esc(name)}</b> как «не ходит»?", reply_markup=confirm_keyboard())
        return

    if action == IntentAction.STUDENT_DELETE:
        if not intent.student_name:
            await _ask_clarification(message, state, "Укажите ФИО ученика.", intent, "student_name")
            return
        name, row_num, ambiguous = await students_svc.resolve_student(intent.student_name)
        if ambiguous:
            await message.answer("Уточните:\n" + "\n".join(f"• {esc(n)}" for n in ambiguous))
            return
        if name is None:
            await message.answer(f"Ученик <b>«{esc(intent.student_name)}»</b> не найден.")
            return
        await state.set_state(ConfirmAction.waiting)
        await state.update_data(action="delete_student", student_name=name, row_num=row_num)
        await message.answer(
            f"⚠️ Удалить ученика <b>{esc(name)}</b> из класса? Это необратимо.",
            reply_markup=confirm_keyboard("Удалить 🗑", "Отменить ❌"),
        )
        return

    if action == IntentAction.STUDENT_LIST:
        result = await students_svc.format_student_list(
            include_birthdays=intent.include_birthdays,
            include_ages=intent.include_ages,
        )
        await message.answer(result)
        return

    if action == IntentAction.STUDENT_COUNT:
        total, active = await students_svc.count_students()
        await message.answer(
            f"В классе <b>{total}</b> учеников ({active} активных, {total - active} не ходят)."
        )
        return

    if action == IntentAction.STUDENT_COUNT_GENDER:
        from sheets.schema import GENDER_FEMALE, parse_gender
        gender = parse_gender(intent.gender) or GENDER_FEMALE
        await message.answer(await students_svc.count_by_gender(gender))
        return

    # ── Финансы ───────────────────────────────────────────────────────────

    if action == IntentAction.CONTRIBUTION_ADD:
        if not intent.student_name:
            await _ask_clarification(message, state, "Укажите ФИО ученика.", intent, "student_name")
            return
        if not intent.amount:
            await _ask_clarification(
                message, state,
                f"Укажите сумму взноса для <b>{esc(intent.student_name)}</b>.",
                intent, "amount",
            )
            return
        _, result = await finance_svc.add_contribution(
            intent.student_name, intent.purpose or "без назначения", intent.amount
        )
        await message.answer(result)
        return

    if action == IntentAction.CONTRIBUTION_ALL:
        amount = intent.per_student_amount or intent.amount
        if not amount:
            await _ask_clarification(
                message, state, "Укажите сумму взноса на одного ученика.", intent, "per_student_amount"
            )
            return
        result = await finance_svc.contribution_all_students(
            intent.purpose or "без назначения", amount
        )
        await message.answer(result)
        return

    if action == IntentAction.CONTRIBUTION_CLEAR:
        if not intent.student_name:
            await _ask_clarification(message, state, "Укажите ФИО ученика.", intent, "student_name")
            return
        if not intent.purpose:
            await _ask_clarification(message, state, "Укажите назначение взноса.", intent, "purpose")
            return
        result = await finance_svc.clear_student_contribution(intent.student_name, intent.purpose)
        await message.answer(result)
        return

    if action == IntentAction.EXPENSE_ADD:
        if not intent.purpose:
            await _ask_clarification(message, state, "Укажите назначение траты.", intent, "purpose")
            return
        if not intent.amount:
            await _ask_clarification(
                message, state,
                f"Укажите общую сумму траты на «{esc(intent.purpose)}».",
                intent, "amount",
            )
            return
        result = await finance_svc.add_expense_general(intent.purpose, intent.amount)
        await message.answer(result)
        return

    if action == IntentAction.EXPENSE_SPLIT:
        if not intent.purpose:
            await _ask_clarification(message, state, "Укажите назначение траты.", intent, "purpose")
            return
        if not intent.amount:
            await _ask_clarification(
                message, state,
                f"Укажите общую сумму для разделения на «{esc(intent.purpose)}».",
                intent, "amount",
            )
            return
        result = await finance_svc.split_expense(intent.purpose, intent.amount)
        await message.answer(result)
        return

    if action == IntentAction.EXPENSE_PER_STUDENT:
        if not intent.purpose:
            await _ask_clarification(message, state, "Укажите назначение траты.", intent, "purpose")
            return
        amount = intent.per_student_amount or intent.amount
        if not amount:
            await _ask_clarification(
                message, state,
                f"Укажите сумму на одного ученика для «{esc(intent.purpose)}».",
                intent, "per_student_amount",
            )
            return
        result = await finance_svc.expense_per_student(intent.purpose, amount)
        await message.answer(result)
        return

    if action in (IntentAction.CONTRIBUTION_DELETE_ALL, IntentAction.EXPENSE_DELETE_ALL):
        kind = "взноса" if action == IntentAction.CONTRIBUTION_DELETE_ALL else "траты"
        prefix = CONTRIB_PREFIX if action == IntentAction.CONTRIBUTION_DELETE_ALL else EXPENSE_PREFIX
        if not intent.purpose:
            await _ask_clarification(
                message, state, f"Укажите назначение {kind} для удаления.", intent, "purpose"
            )
            return
        col_idx, col_name = await finance_svc.find_column_by_purpose(intent.purpose, prefix=prefix)
        if col_idx is None:
            await message.answer(f"Столбец «{prefix}{esc(intent.purpose)}» не найден в «Финансы».")
            return
        await state.set_state(ConfirmAction.waiting)
        await state.update_data(action="delete_finance_column", col_idx=col_idx, purpose=col_name)
        await message.answer(
            f"⚠️ Удалить столбец <b>«{esc(col_name)}»</b> из листа «Финансы»? "
            "Все данные по этому назначению будут потеряны.",
            reply_markup=confirm_keyboard("Удалить 🗑", "Отменить ❌"),
        )
        return

    # ── Отчёты ────────────────────────────────────────────────────────────

    if action == IntentAction.REPORT_BALANCE:
        await message.answer(await reports_svc.report_balance())
        return
    if action == IntentAction.REPORT_CONTRIBUTIONS_TOTAL:
        await message.answer(await reports_svc.report_contributions_total())
        return
    if action == IntentAction.REPORT_EXPENSES_TOTAL:
        await message.answer(await reports_svc.report_expenses_total())
        return
    if action == IntentAction.REPORT_FULL:
        await message.answer(await reports_svc.report_full())
        return
    if action == IntentAction.REPORT_CONTRIBUTIONS_LIST:
        await message.answer(await reports_svc.report_contributions_list())
        return
    if action == IntentAction.REPORT_CONTRIBUTIONS_BY_STUDENT:
        await message.answer(await reports_svc.report_contributions_by_student())
        return
    if action == IntentAction.REPORT_EXPENSES_LIST:
        await message.answer(await reports_svc.report_expenses_list())
        return

    if action == IntentAction.REPORT_CLASS_FINANCE:
        await message.answer(await reports_svc.report_class_finance())
        return

    if action == IntentAction.REPORT_STUDENT:
        if not intent.student_name:
            await _ask_clarification(message, state, "Укажите имя ученика.", intent, "student_name")
            return
        await message.answer(await reports_svc.report_student(intent.student_name))
        return

    if action == IntentAction.REPORT_PAID:
        await message.answer(
            await reports_svc.report_paid(intent.purpose, intent.filter_paid is not False)
        )
        return

    # ── Контакты ──────────────────────────────────────────────────────────

    if action == IntentAction.CONTACT_PHONE:
        if not intent.student_name:
            await _ask_clarification(message, state, "Укажите имя ученика.", intent, "student_name")
            return
        await message.answer(await contacts_svc.get_phone(intent.student_name))
        return

    # ── Дни рождения ──────────────────────────────────────────────────────

    if action == IntentAction.BIRTHDAY_UPCOMING:
        await message.answer(await bday_svc.upcoming_birthdays(intent.days_ahead))
        return
    if action == IntentAction.BIRTHDAY_LIST:
        await message.answer(await bday_svc.birthday_list(include_ages=intent.include_ages))
        return
    if action == IntentAction.BIRTHDAY_BY_MONTH:
        await message.answer(await bday_svc.birthdays_by_month())
        return

    # ── Системные ─────────────────────────────────────────────────────────

    if action == IntentAction.HELP:
        from bot.handlers.system import HELP_TEXT
        await message.answer(HELP_TEXT)
        return
    if action == IntentAction.RESET:
        await state.clear()
        await message.answer("🔄 Контекст очищен.")
        return

    await message.answer("🤔 Не понял запрос. Попробуйте переформулировать или введите /help.")


# ── Catch-all для прочих FSM-состояний ───────────────────────────────────

@router.message()
async def fsm_in_progress(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current and current.startswith("AddStudentForm"):
        await message.answer("Идёт диалог добавления ученика. Введите ответ или /cancel для отмены.")
    else:
        await message.answer("Введите /cancel для выхода из текущего диалога.")
