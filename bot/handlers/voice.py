"""
Обработчик голосовых сообщений.

Поток:
  1. Скачиваем OGG/Opus файл из Telegram
  2. Транскрибируем через Whisper (openai / custom)
  3. Показываем пользователю распознанный текст
  4. Прогоняем текст через parse_intent → _safe_dispatch (как обычное сообщение)

При STT_BACKEND=disabled голосовые сообщения отклоняются без транскрипции.
"""

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import Message

from config import STTBackend, settings
from llm.client import parse_intent
from stt.client import transcribe

from .messages import _safe_dispatch

log = logging.getLogger(__name__)
router = Router(name="voice")


@router.message(StateFilter(default_state), F.voice)
async def handle_voice(message: Message, state: FSMContext) -> None:
    if settings.stt_backend == STTBackend.DISABLED:
        await message.answer("🎙 Голосовые сообщения отключены. Напишите запрос текстом.")
        return

    thinking = await message.answer("🎙 Распознаю голосовое…")

    # Скачиваем аудиофайл
    try:
        tg_file = await message.bot.get_file(message.voice.file_id)
        buf = await message.bot.download_file(tg_file.file_path)
        voice_bytes = buf.read()
    except Exception as exc:
        log.error("STT: ошибка загрузки файла: %s", exc)
        await thinking.edit_text("⚠️ Не удалось загрузить голосовое сообщение.")
        return

    # Транскрибируем
    try:
        text = await transcribe(voice_bytes)
    except Exception as exc:
        log.error("STT: ошибка транскрипции: %s", exc)
        await thinking.edit_text(
            "⚠️ Не удалось распознать речь.\n"
            "Убедитесь, что STT-сервер доступен и модель загружена."
        )
        return

    if not text:
        await thinking.edit_text("🎙 Не удалось разобрать речь — попробуйте ещё раз.")
        return

    # Показываем распознанный текст и обрабатываем
    await thinking.edit_text(f"🎙 <i>«{text}»</i>\n⏳")

    try:
        intent = await parse_intent(text)
    except Exception as exc:
        log.error("STT → parse_intent: %s", exc)
        await thinking.edit_text(f"🎙 <i>«{text}»</i>\n⚠️ Не удалось разобрать запрос.")
        return

    await thinking.delete()
    log.info("STT → интент: action=%s | %s", intent.action, intent.raw_intent)
    await _safe_dispatch(message, state, intent)
