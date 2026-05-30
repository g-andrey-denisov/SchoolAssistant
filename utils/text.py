"""Утилиты форматирования текста для Telegram (parse_mode=HTML)."""

from html import escape


def esc(value) -> str:
    """
    Экранирует динамическое значение для безопасной вставки в HTML-сообщение.
    Символы < > & в именах/назначениях/примечаниях иначе ломают разбор entities
    на стороне Telegram и приводят к ошибке отправки.
    """
    if value is None:
        return ""
    return escape(str(value), quote=False)
