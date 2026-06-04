"""
Сверка списков учеников: парсинг внешнего списка (текст / .txt / .csv / .xlsx)
и сравнение его с тем, что хранится в БД (лист «Контакты»).

Формат внешнего списка:
  • Текст / .txt — по одному ученику в строке (только ФИО), допустимы
    нумерация и маркеры списка («1. », «- », «• »).
  • .csv / .xlsx — таблица. Колонки распознаются по заголовкам:
    ФИО, Пол, День рождения, ФИО родителя, Телефон. Если строки-заголовка
    нет — первый столбец считается ФИО ученика.

Парсеры возвращают список словарей с ключами COL_* (как в sheets.schema),
поэтому результат напрямую совместим с services.students.add_student.
"""

import csv
import datetime
import io
import logging
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, utils as fuzz_utils

from sheets.schema import (
    COL_BIRTHDAY, COL_GENDER, COL_PARENT_NAME, COL_PARENT_PHONE, COL_STUDENT,
    parse_gender,
)

log = logging.getLogger(__name__)

# Порог совпадения ФИО при сверке. Выше, чем общий THRESHOLD поиска (68),
# чтобы разные ученики с похожими фамилиями не схлопывались в один.
ROSTER_MATCH_THRESHOLD = 85

_BULLET_RE = re.compile(r"^\s*(?:\d+[.)]\s*|[-•*]\s*)")


# ── Распознавание колонок таблицы ────────────────────────────────────────────

def _classify_header(cell: str) -> str | None:
    """По тексту заголовка определяет, какому полю соответствует колонка."""
    s = cell.strip().lower()
    if not s:
        return None
    # Телефон проверяем раньше «родителя»: «Телефон родителя» → телефон.
    if any(k in s for k in ("телефон", "тел.", "номер", "контакт", "моб")):
        return COL_PARENT_PHONE
    if any(k in s for k in ("родител", "мама", "папа", "мать", "отец", "представит")):
        return COL_PARENT_NAME
    if "рожд" in s or "дата" in s or s in ("др", "д.р", "д.р."):
        return COL_BIRTHDAY
    if s == "пол" or s.startswith("пол "):
        return COL_GENDER
    if any(k in s for k in (
        "фио", "ф.и.о", "ученик", "фамил", "имя",
        "ребён", "ребен", "студент",
    )):
        return COL_STUDENT
    return None


def _fmt_date(value) -> str:
    """Дату из ячейки приводит к строке ДД.ММ.ГГГГ."""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime("%d.%m.%Y")
    return str(value).strip()


def _fmt_cell(value, col: str) -> str:
    if value is None:
        return ""
    if col == COL_GENDER:
        return parse_gender(str(value)) or ""
    if col == COL_BIRTHDAY:
        return _fmt_date(value)
    return str(value).strip()


def _rows_to_entries(rows: list[list]) -> list[dict]:
    """Таблицу (list строк) превращает в список словарей-учеников."""
    rows = [r for r in rows if any(str(c).strip() for c in r if c is not None)]
    if not rows:
        return []

    # Ищем строку-заголовок среди первых пяти строк.
    header_idx: int | None = None
    colmap: dict[int, str] = {}
    for i, row in enumerate(rows[:5]):
        mapping = {}
        for j, cell in enumerate(row):
            cls = _classify_header(str(cell) if cell is not None else "")
            if cls and cls not in mapping.values():
                mapping[j] = cls
        if COL_STUDENT in mapping.values():
            header_idx, colmap = i, mapping
            break

    # Заголовок не найден — считаем, что первый столбец это ФИО, без шапки.
    if header_idx is None:
        entries = []
        for row in rows:
            name = str(row[0]).strip() if row and row[0] is not None else ""
            if name:
                entries.append({COL_STUDENT: name})
        return entries

    name_col = next(j for j, v in colmap.items() if v == COL_STUDENT)
    entries = []
    for row in rows[header_idx + 1:]:
        name = str(row[name_col]).strip() if name_col < len(row) and row[name_col] is not None else ""
        if not name:
            continue
        entry = {COL_STUDENT: name}
        for j, col in colmap.items():
            if col == COL_STUDENT or j >= len(row):
                continue
            val = _fmt_cell(row[j], col)
            if val:
                entry[col] = val
        entries.append(entry)
    return entries


# ── Публичные парсеры ────────────────────────────────────────────────────────

def parse_text_lines(text: str) -> list[dict]:
    """Текст «по ученику в строке» → список словарей (только ФИО)."""
    entries = []
    for line in text.splitlines():
        s = _BULLET_RE.sub("", line.strip()).strip()
        if s:
            entries.append({COL_STUDENT: s})
    return entries


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_csv(data: bytes) -> list[dict]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    return _rows_to_entries(rows)


def parse_xlsx(data: bytes) -> list[dict]:
    import openpyxl  # тяжёлый импорт — только когда реально нужен xlsx

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = [list(row) for row in ws.iter_rows(values_only=True)]
    wb.close()
    return _rows_to_entries(rows)


SUPPORTED_EXTS = (".txt", ".csv", ".xlsx", ".xlsm")


def parse_roster(filename: str, data: bytes) -> list[dict]:
    """Диспетчер по расширению файла. Бросает ValueError для неподдержанных."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return parse_xlsx(data)
    if name.endswith(".csv"):
        return parse_csv(data)
    if name.endswith(".txt"):
        return parse_text_lines(_decode(data))
    raise ValueError(
        f"Формат файла не поддержан. Пришлите .txt, .csv или .xlsx "
        f"(получен «{filename}»)."
    )


# ── Сравнение списков ────────────────────────────────────────────────────────

@dataclass
class Comparison:
    to_add: list[dict] = field(default_factory=list)            # есть в списке, нет в БД
    to_remove: list[tuple[int, str]] = field(default_factory=list)  # (row_num, ФИО) есть в БД, нет в списке
    matched: list[tuple[str, str]] = field(default_factory=list)    # (имя_из_списка, имя_в_БД)
    new_total: int = 0
    db_total: int = 0


def compare(new_entries: list[dict], db_indexed: list[tuple[int, dict]]) -> Comparison:
    """
    Сопоставляет внешний список с учениками БД по ФИО (нечётко).
    db_indexed — результат get_contacts_indexed(): [(row_num, row_dict), ...].
    """
    db = [
        (row_num, (row.get(COL_STUDENT, "") or "").strip())
        for row_num, row in db_indexed
    ]
    db = [(rn, n) for rn, n in db if n]

    matched_idx: set[int] = set()
    result = Comparison(new_total=len(new_entries), db_total=len(db))

    for entry in new_entries:
        query = entry.get(COL_STUDENT, "").strip()
        if not query:
            continue
        q_proc = fuzz_utils.default_process(query)
        best_i, best_score = None, 0.0
        for i, (_, name) in enumerate(db):
            if i in matched_idx:
                continue
            score = fuzz.token_set_ratio(
                q_proc, fuzz_utils.default_process(name)
            )
            if score > best_score:
                best_i, best_score = i, score
        if best_i is not None and best_score >= ROSTER_MATCH_THRESHOLD:
            matched_idx.add(best_i)
            result.matched.append((query, db[best_i][1]))
        else:
            result.to_add.append(entry)

    result.to_remove = [
        (rn, name) for i, (rn, name) in enumerate(db) if i not in matched_idx
    ]
    log.info(
        "Сверка списков: новый=%d, БД=%d, добавить=%d, удалить=%d, совпало=%d",
        result.new_total, result.db_total,
        len(result.to_add), len(result.to_remove), len(result.matched),
    )
    return result
