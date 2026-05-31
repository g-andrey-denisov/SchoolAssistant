"""
STT-клиент: транскрибирует голосовое сообщение через Whisper.

Использует OpenAI-совместимый эндпоинт /v1/audio/transcriptions (multipart):
  - если задан STT_BASE_URL — шлём туда (любой OpenAI-совместимый whisper-сервер);
  - иначе — облачный OpenAI API по openai_api_key.

Внимание: LM Studio НЕ предоставляет эндпоинт транскрипции, поэтому для STT
нужен либо OpenAI, либо отдельный whisper-сервер (speaches/whisper.cpp).
"""

import io
import logging

from openai import AsyncOpenAI

from config import settings

log = logging.getLogger(__name__)


def _make_stt_client() -> AsyncOpenAI:
    if settings.stt_base_url:
        # Локальный/сторонний OpenAI-совместимый whisper-сервер
        return AsyncOpenAI(
            base_url=settings.stt_base_url,
            api_key=settings.openai_api_key or "not-needed",
            timeout=settings.stt_timeout,
        )
    # Облачный OpenAI
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.stt_timeout,
    )


_stt_client: AsyncOpenAI = _make_stt_client()


async def transcribe(voice_bytes: bytes) -> str:
    """
    Транскрибирует OGG/Opus аудио (из Telegram) в текст.
    Возвращает пустую строку, если распознавание не дало результата.
    """
    audio = io.BytesIO(voice_bytes)
    audio.name = "voice.ogg"  # Whisper определяет формат по расширению

    log.debug("STT: отправляю %d байт на транскрипцию (модель=%s)", len(voice_bytes), settings.stt_model)

    response = await _stt_client.audio.transcriptions.create(
        model=settings.stt_model,
        file=audio,
        language="ru",
    )
    text = (response.text or "").strip()
    log.info("STT: распознано %r", text[:120])
    return text
