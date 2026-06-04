"""Константы: имена листов и заголовков столбцов."""

from config import settings


# ── Листы ──────────────────────────────────────────────────────────────────
def SHEET_CONTACTS() -> str:
    return settings.sheet_contacts

def SHEET_FINANCES() -> str:
    return settings.sheet_finances


# ── Первый столбец обоих листов ────────────────────────────────────────────
COL_STUDENT = "ФИО ученика"

# ── Лист «Контакты» ────────────────────────────────────────────────────────
COL_BIRTHDAY    = "День рождения"
COL_PARENT_NAME = "ФИО родителя"
COL_PARENT_PHONE = "Телефон"
COL_NOTE        = "Примечание"
COL_GENDER      = "Пол"

# Если это слово содержится в Примечании — ученик неактивен
INACTIVE_MARKER = "не ходит"

# Порядок столбцов листа «Контакты». Маппинг строго позиционный
# (_map_contacts_row / append_contact), поэтому порядок здесь ОБЯЗАН
# совпадать с порядком столбцов в самой Google-таблице.
# COL_GENDER стоит вторым — между «ФИО ученика» и «День рождения».
CONTACTS_COLUMNS = [COL_STUDENT, COL_GENDER, COL_BIRTHDAY, COL_PARENT_NAME, COL_PARENT_PHONE, COL_NOTE]

# ── Пол ученика ──────────────────────────────────────────────────────────────
# В таблице хранится одной буквой: «М» / «Ж».
GENDER_MALE   = "М"
GENDER_FEMALE = "Ж"

_MALE_TOKENS = {"м", "муж", "мужской", "мальчик", "male", "boy", "m"}
_FEMALE_TOKENS = {"ж", "жен", "женский", "девочка", "female", "girl", "f", "w"}


def parse_gender(text: str | None) -> str | None:
    """Нормализует свободный ввод/хранимое значение к «М»/«Ж» или None."""
    if not text:
        return None
    t = text.strip().lower().rstrip(".")
    if t in _MALE_TOKENS:
        return GENDER_MALE
    if t in _FEMALE_TOKENS:
        return GENDER_FEMALE
    return None


def is_male(value: str | None) -> bool:
    return parse_gender(value) == GENDER_MALE


def is_female(value: str | None) -> bool:
    return parse_gender(value) == GENDER_FEMALE

# ── Лист «Финансы» ─────────────────────────────────────────────────────────
# Первый столбец = COL_STUDENT (фиксирован)
# Остальные столбцы создаются динамически:
#   «Взнос: <назначение>»  — ученик заплатил  → значения > 0
#   «Трата: <назначение>»  — потрачено на ученика → значения > 0
# Остаток = Σ взносов − Σ трат

CONTRIB_PREFIX = "Взнос: "
EXPENSE_PREFIX = "Трата: "
