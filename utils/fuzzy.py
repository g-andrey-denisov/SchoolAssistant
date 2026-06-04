"""Нечёткое сопоставление имён через rapidfuzz."""

from rapidfuzz import fuzz, process, utils as fuzz_utils

# token_set_ratio: 100 когда запрос — подмножество токенов кандидата.
# Это нужно, чтобы «Петров» находил «Петров Алексей Иванович».
_SCORER = fuzz.token_set_ratio

THRESHOLD = 68       # минимальный балл совпадения
AMBIGUITY_GAP = 10   # разрыв баллов для однозначного выбора


def find_best_match(query: str, candidates: list[str]) -> tuple[str | None, float]:
    """Возвращает (лучшее совпадение, балл) или (None, 0.0)."""
    if not candidates or not query:
        return None, 0.0
    result = process.extractOne(
        query, candidates,
        scorer=_SCORER,
        processor=fuzz_utils.default_process,
        score_cutoff=THRESHOLD,
    )
    if result:
        return result[0], float(result[1])
    return None, 0.0


def find_best_with_ambiguity(
    query: str,
    candidates: list[str],
) -> tuple[str | None, list[str]]:
    """
    Возвращает (однозначное совпадение, []) или (None, [варианты...]).
    Нет совпадений → (None, []).
    """
    if not candidates or not query:
        return None, []

    results = process.extract(
        query, candidates,
        scorer=_SCORER,
        processor=fuzz_utils.default_process,
        limit=4,
        score_cutoff=THRESHOLD,
    )
    if not results:
        return None, []

    if len(results) == 1:
        return results[0][0], []

    top_score = results[0][1]
    second_score = results[1][1]

    # Если первый вариант заметно лучше второго — считаем однозначным
    if top_score - second_score >= AMBIGUITY_GAP:
        return results[0][0], []

    return None, [r[0] for r in results]


def fuzzy_purpose_match(query: str, purpose: str) -> bool:
    """Проверяет, описывает ли query то же назначение, что и purpose."""
    score = fuzz.token_set_ratio(query.lower(), purpose.lower())
    return score >= THRESHOLD
