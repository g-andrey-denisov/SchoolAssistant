"""Pydantic-модели для структурированных интентов."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IntentAction(StrEnum):
    # ── Ученики ───────────────────────────────────────────────────────────
    STUDENT_ADD = "student_add"
    STUDENT_MARK_INACTIVE = "student_mark_inactive"
    STUDENT_DELETE = "student_delete"
    STUDENT_LIST = "student_list"
    STUDENT_COUNT = "student_count"
    STUDENT_COUNT_GENDER = "student_count_gender"  # «Сколько девочек / мальчиков»

    # ── Финансы ───────────────────────────────────────────────────────────
    CONTRIBUTION_ADD = "contribution_add"        # «Петров сдал 500 на подарки»
    CONTRIBUTION_ALL = "contribution_all"        # «Весь класс сдал на полки по 120 руб»
    CONTRIBUTION_CLEAR = "contribution_clear"    # «Тестов не сдал / удали взнос Тестова»
    EXPENSE_ADD = "expense_add"                  # общеклассовая трата, одна запись
    EXPENSE_SPLIT = "expense_split"              # общая сумма ÷ кол-во активных
    EXPENSE_PER_STUDENT = "expense_per_student"  # каждому ученику по N рублей
    CONTRIBUTION_DELETE_ALL = "contribution_delete_all"
    EXPENSE_DELETE_ALL = "expense_delete_all"

    # ── Отчёты ────────────────────────────────────────────────────────────
    REPORT_BALANCE = "report_balance"
    REPORT_CONTRIBUTIONS_TOTAL = "report_contributions_total"
    REPORT_EXPENSES_TOTAL = "report_expenses_total"
    REPORT_FULL = "report_full"
    REPORT_CONTRIBUTIONS_LIST = "report_contributions_list"           # по назначениям
    REPORT_CONTRIBUTIONS_BY_STUDENT = "report_contributions_by_student"  # по ученикам
    REPORT_EXPENSES_LIST = "report_expenses_list"
    REPORT_STUDENT = "report_student"
    REPORT_CLASS_FINANCE = "report_class_finance"  # «Финансовый отчёт класса»
    REPORT_PAID = "report_paid"

    # ── Контакты ──────────────────────────────────────────────────────────
    CONTACT_PHONE = "contact_phone"

    # ── Дни рождения ──────────────────────────────────────────────────────
    BIRTHDAY_UPCOMING = "birthday_upcoming"
    BIRTHDAY_LIST = "birthday_list"
    BIRTHDAY_BY_MONTH = "birthday_by_month"  # «Дни рождения по месяцам»

    # ── Системные ─────────────────────────────────────────────────────────
    HELP = "help"
    RESET = "reset"
    UNKNOWN = "unknown"


class SheetIntent(BaseModel):
    action: IntentAction = Field(description="Что нужно сделать")

    # Ученик
    student_name: str | None = Field(default=None, description="ФИО ученика")
    gender: str | None = Field(
        default=None, description="Пол: 'м' (мальчики) или 'ж' (девочки)"
    )
    birthday: str | None = Field(default=None, description="Дата рождения DD.MM.YYYY")
    parent_name: str | None = Field(default=None, description="ФИО родителя")
    parent_phone: str | None = Field(default=None, description="Телефон родителя")
    note: str | None = Field(default=None, description="Примечание к ученику")

    # Финансы
    purpose: str | None = Field(default=None, description="Назначение (на что платят/тратят)")
    amount: float | None = Field(default=None, description="Сумма (общая или для одного ученика)")
    per_student_amount: float | None = Field(
        default=None, description="Сумма на одного ученика (для expense_per_student)"
    )

    # Отчёт «кто сдал/не сдал»
    filter_paid: bool | None = Field(
        default=None, description="True = кто сдал, False = кто не сдал"
    )

    # Список учеников
    include_birthdays: bool = Field(default=False, description="Включить дни рождения в список")
    include_ages: bool = Field(default=False, description="Включить возраст в список")

    # Дни рождения
    days_ahead: int = Field(default=30, description="Горизонт поиска ДР в днях")

    # Дизамбигуация
    clarification_needed: bool = False
    clarification_question: str | None = None
    raw_intent: str | None = Field(default=None, description="Краткое описание для логов")
