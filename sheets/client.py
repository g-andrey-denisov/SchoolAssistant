"""
Асинхронная обёртка над gspread.
Все синхронные вызовы выполняются в thread-pool executor.

Модель данных:
  «Контакты»: ФИО ученика | День рождения | ФИО родителя | Телефон | Примечание
  «Финансы»:  ФИО ученика | <столбец на событие> | ...
               +N = взнос ученика, −N = трата на ученика
"""

import asyncio
import logging
from functools import partial
from typing import Any

import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials

from config import settings
from sheets.schema import (
    CONTACTS_COLUMNS, COL_NOTE, COL_PARENT_NAME, COL_PARENT_PHONE, COL_STUDENT,
    SHEET_CONTACTS, SHEET_FINANCES,
)

log = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _to_float(value: Any) -> float:
    if not value and value != 0:
        return 0.0
    try:
        return float(str(value).replace(",", ".").replace(" ", "").replace(" ", ""))
    except (ValueError, TypeError):
        return 0.0


class SheetsClient:
    def __init__(self) -> None:
        creds = Credentials.from_service_account_file(
            str(settings.google_credentials_file), scopes=_SCOPES
        )
        self._gc = gspread.authorize(creds)
        self._sid = settings.google_spreadsheet_id
        log.info("SheetsClient готов (spreadsheet=%s)", self._sid)

    # ── Общие внутренние хелперы ─────────────────────────────────────────

    async def _run(self, func, *args, **kwargs) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def _open_ws(self, sheet_name: str) -> gspread.Worksheet:
        spreadsheet = await self._run(self._gc.open_by_key, self._sid)
        return await self._run(spreadsheet.worksheet, sheet_name)

    async def _get_rows_indexed(
        self, sheet_name: str
    ) -> tuple[list[str], list[tuple[int, dict]]]:
        """
        (заголовки, [(row_num_1based, row_dict), ...])

        Первый столбец всегда доступен по ключу COL_STUDENT («ФИО ученика»),
        даже если в таблице заголовок написан иначе.
        """
        ws = await self._open_ws(sheet_name)
        all_values: list[list[str]] = await self._run(ws.get_all_values)
        if not all_values:
            return [], []
        headers = all_values[0]
        log.info("Лист «%s» заголовки: %s", sheet_name, headers)

        rows = []
        for i, row in enumerate(all_values[1:]):
            row_dict = {headers[j]: (row[j] if j < len(row) else "") for j in range(len(headers))}
            # Нормализация: первый столбец всегда доступен как COL_STUDENT
            if headers and headers[0] != COL_STUDENT:
                row_dict[COL_STUDENT] = row[0] if row else ""
            rows.append((i + 2, row_dict))

        return headers, rows

    # ── Лист «Контакты» ──────────────────────────────────────────────────

    def _map_contacts_row(self, raw_row: list[str]) -> dict:
        """
        Маппинг по ПОЗИЦИИ к именам CONTACTS_COLUMNS.
        Работает независимо от того, как названы заголовки в таблице.
        """
        return {
            CONTACTS_COLUMNS[j] if j < len(CONTACTS_COLUMNS) else f"col_{j}":
            (raw_row[j] if j < len(raw_row) else "")
            for j in range(max(len(CONTACTS_COLUMNS), len(raw_row)))
        }

    async def _get_contacts_raw(self) -> tuple[list[str], list[list[str]]]:
        """Возвращает (headers, data_rows) без обработки."""
        ws = await self._open_ws(SHEET_CONTACTS())
        all_values: list[list[str]] = await self._run(ws.get_all_values)
        if not all_values:
            return [], []
        log.info("Лист «%s» заголовки: %s", SHEET_CONTACTS(), all_values[0])
        return all_values[0], all_values[1:]

    @staticmethod
    def _fill_down_parent_info(rows: list[dict]) -> list[dict]:
        """
        Распространяет ФИО родителя и Телефон вниз по пустым ячейкам.
        Нужно когда ячейки объединены в Google Sheets для братьев/сестёр:
        get_all_values() возвращает значение только в первой строке объединения,
        остальные строки приходят пустыми.
        """
        last_parent = ""
        last_phone = ""
        for row in rows:
            pn = row.get(COL_PARENT_NAME, "").strip()
            ph = row.get(COL_PARENT_PHONE, "").strip()

            if pn:
                last_parent = pn
            elif last_parent and row.get(COL_STUDENT, "").strip():
                # Заполняем только если в строке есть ФИО ученика
                row[COL_PARENT_NAME] = last_parent
                log.debug("fill-down родитель: %s -> %s", row[COL_STUDENT], last_parent)

            if ph:
                last_phone = ph
            elif last_phone and row.get(COL_STUDENT, "").strip():
                row[COL_PARENT_PHONE] = last_phone

        return rows

    async def get_contacts(self) -> list[dict]:
        _, data_rows = await self._get_contacts_raw()
        mapped = [self._map_contacts_row(row) for row in data_rows]
        return self._fill_down_parent_info(mapped)

    async def get_contacts_indexed(self) -> list[tuple[int, dict]]:
        _, data_rows = await self._get_contacts_raw()
        pairs = [(i + 2, self._map_contacts_row(row)) for i, row in enumerate(data_rows)]
        self._fill_down_parent_info([row for _, row in pairs])
        return pairs

    async def append_contact(self, data: dict) -> None:
        ws = await self._open_ws(SHEET_CONTACTS())
        row = [data.get(col, "") for col in CONTACTS_COLUMNS]
        await self._run(ws.append_row, row, value_input_option="USER_ENTERED")
        log.info("Добавлен контакт: %s", data.get(COL_STUDENT))

    async def update_contact_cell(self, row_num: int, col_name: str, value: str) -> None:
        # Позиция колонки определяется по CONTACTS_COLUMNS, не по заголовку таблицы
        if col_name in CONTACTS_COLUMNS:
            col_idx = CONTACTS_COLUMNS.index(col_name) + 1
        else:
            headers, _ = await self._get_contacts_raw()
            try:
                col_idx = headers.index(col_name) + 1
            except ValueError:
                raise ValueError(f"Столбец «{col_name}» не найден в «{SHEET_CONTACTS()}»")
        ws = await self._open_ws(SHEET_CONTACTS())
        await self._run(ws.update_cell, row_num, col_idx, value)
        log.info("Контакт строка %d, col%d (%s) = %r", row_num, col_idx, col_name, value)

    async def delete_contact_row(self, row_num: int) -> None:
        ws = await self._open_ws(SHEET_CONTACTS())
        await self._run(ws.delete_rows, row_num)
        log.info("Удалена строка контакта: %d", row_num)

    # ── Лист «Финансы» ───────────────────────────────────────────────────

    async def get_finance_data(self) -> tuple[list[str], list[tuple[int, dict]]]:
        """(заголовки_включая_ФИО, [(row_num, row_dict), ...])"""
        return await self._get_rows_indexed(SHEET_FINANCES())

    async def get_finance_column_idx(self, purpose: str) -> int | None:
        """Точное совпадение заголовка. Возвращает 1-based индекс или None."""
        headers, _ = await self.get_finance_data()
        try:
            return headers.index(purpose) + 1
        except ValueError:
            return None

    async def get_or_create_finance_column(self, purpose: str) -> int:
        """Находит или создаёт столбец. Возвращает 1-based индекс."""
        headers, _ = await self.get_finance_data()
        if purpose in headers:
            return headers.index(purpose) + 1
        # Создаём новый столбец — добавляем заголовок в следующую пустую колонку
        ws = await self._open_ws(SHEET_FINANCES())
        new_col_idx = len(headers) + 1
        await self._run(ws.update_cell, 1, new_col_idx, purpose)
        log.info("Создан столбец «%s» (col=%d) в «%s»", purpose, new_col_idx, SHEET_FINANCES())
        return new_col_idx

    async def batch_update_finance_column(
        self,
        purpose: str,
        student_deltas: dict[str, float],
    ) -> None:
        """
        Для каждого ученика из student_deltas прибавляет delta к его ячейке
        в столбце purpose. Столбец создаётся при необходимости.
        """
        ws = await self._open_ws(SHEET_FINANCES())
        all_values: list[list[str]] = await self._run(ws.get_all_values)
        if not all_values:
            log.warning("Лист «%s» пуст", SHEET_FINANCES())
            return

        headers = all_values[0]

        # Найти или создать столбец.
        # Сначала точное совпадение, затем регистро-независимое — чтобы не создавать дубли
        # при разном написании (напр. «Нужды класса» vs «нужды класса»).
        purpose_lower = purpose.lower()
        existing = next((h for h in headers if h.lower() == purpose_lower), None)
        if existing:
            col_idx = headers.index(existing) + 1
            if existing != purpose:
                log.debug("Найдена похожая колонка «%s» вместо «%s»", existing, purpose)
        else:
            col_idx = len(headers) + 1
            await self._run(ws.update_cell, 1, col_idx, purpose)
            headers.append(purpose)
            log.info("Создан столбец «%s» col=%d", purpose, col_idx)

        # Собрать batch-обновления
        updates = []
        for row_i, row in enumerate(all_values[1:], start=2):
            student_name = row[0] if row else ""
            if student_name not in student_deltas:
                continue
            current = _to_float(row[col_idx - 1] if col_idx - 1 < len(row) else "")
            new_val = round(current + student_deltas[student_name], 2)
            updates.append({"range": rowcol_to_a1(row_i, col_idx), "values": [[new_val]]})

        if updates:
            await self._run(
                ws.batch_update, updates, value_input_option="USER_ENTERED"
            )
            log.info("batch_update «%s»: %d ячеек", purpose, len(updates))

    async def update_finance_student_cell(
        self,
        student_name: str,
        col_name: str,
        value: float | str,
    ) -> bool:
        """
        Обновляет ячейку конкретного ученика в указанном столбце.
        Возвращает True если строка ученика найдена.
        col_name — полное имя колонки (с префиксом), как оно записано в листе.
        """
        headers, rows = await self.get_finance_data()
        if col_name not in headers:
            return False
        col_idx = headers.index(col_name) + 1
        for row_num, row in rows:
            if row.get(COL_STUDENT, "") == student_name:
                ws = await self._open_ws(SHEET_FINANCES())
                await self._run(ws.update_cell, row_num, col_idx, value)
                log.info("Ячейка [%s / %s] = %r", student_name, col_name, value)
                return True
        log.warning("Строка «%s» не найдена в «Финансы»", student_name)
        return False

    async def get_finance_column_values(self, col_name: str) -> dict[str, float]:
        """Возвращает {ФИО: значение} для столбца с точным именем col_name."""
        headers, rows = await self.get_finance_data()
        if col_name not in headers:
            return {}
        return {
            row.get(COL_STUDENT, ""): _to_float(row.get(col_name, ""))
            for _, row in rows
            if row.get(COL_STUDENT, "")
        }

    async def find_finance_column_fuzzy(
        self,
        purpose: str,
        prefix: str = "",
    ) -> tuple[int | None, str | None]:
        """
        Нечёткий поиск столбца по назначению.
        Если prefix задан — ищет только среди колонок с этим префиксом
        (сравнивает purpose с частью после префикса).
        Возвращает (1-based col_idx, full_col_name) или (None, None).
        """
        from utils.fuzzy import find_best_match
        headers, _ = await self.get_finance_data()
        purpose_headers = headers[1:]  # пропускаем «ФИО ученика»

        if prefix:
            # Кандидаты только с нужным префиксом
            prefixed = [h for h in purpose_headers if h.startswith(prefix)]
            stripped = [h[len(prefix):] for h in prefixed]
            best, _ = find_best_match(purpose, stripped)
            if best:
                full = prefix + best
                return headers.index(full) + 1, full
            # Без fallback по всем колонкам: иначе «удали взнос …» мог бы
            # удалить столбец «Трата: …» и наоборот (потеря данных).
            return None, None
        best, _ = find_best_match(purpose, purpose_headers)
        if best:
            return headers.index(best) + 1, best
        return None, None

    async def clear_finance_column(self, col_idx: int) -> None:
        """Очищает все значения (кроме заголовка) в столбце."""
        ws = await self._open_ws(SHEET_FINANCES())
        all_values: list[list[str]] = await self._run(ws.get_all_values)
        num_rows = len(all_values) - 1  # без заголовка
        if num_rows <= 0:
            return
        updates = [
            {"range": rowcol_to_a1(r, col_idx), "values": [[""]]}
            for r in range(2, num_rows + 2)
        ]
        await self._run(ws.batch_update, updates, value_input_option="USER_ENTERED")
        log.info("Очищен столбец col=%d (%d ячеек)", col_idx, num_rows)

    async def delete_finance_column(self, col_idx: int) -> None:
        """Удаляет столбец целиком."""
        ws = await self._open_ws(SHEET_FINANCES())
        await self._run(ws.delete_columns, col_idx)
        log.info("Удалён столбец col=%d из «%s»", col_idx, SHEET_FINANCES())

    async def append_finance_student_row(self, student_name: str) -> None:
        """Добавляет строку для нового ученика в «Финансы»."""
        ws = await self._open_ws(SHEET_FINANCES())
        await self._run(ws.append_row, [student_name], value_input_option="USER_ENTERED")
        log.info("Добавлена строка в «Финансы»: %s", student_name)

    async def delete_finance_student_row(self, student_name: str) -> None:
        """Удаляет строку ученика из «Финансы»."""
        _, rows = await self.get_finance_data()
        for row_num, row in rows:
            if row.get(COL_STUDENT, "") == student_name:
                ws = await self._open_ws(SHEET_FINANCES())
                await self._run(ws.delete_rows, row_num)
                log.info("Удалена строка «%s» из «Финансы»", student_name)
                return
        log.warning("Строка «%s» не найдена в «Финансы»", student_name)


# ── Синглтон ────────────────────────────────────────────────────────────────

_client: SheetsClient | None = None


def get_client() -> SheetsClient:
    global _client
    if _client is None:
        _client = SheetsClient()
    return _client
