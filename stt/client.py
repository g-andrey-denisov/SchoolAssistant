"""
STT-клиент: транскрибирует голосовое сообщение через Whisper.

STT_BACKEND управляет выбором бэкенда:
  - openai   → облачный OpenAI (OPENAI_API_KEY + STT_MODEL=whisper-1)
  - custom   → сторонний OpenAI-совместимый сервер (STT_BASE_URL + STT_MODEL)
  - disabled → голосовые сообщения отключены (обрабатывается в voice.py)

Внимание: LM Studio НЕ предоставляет эндпоинт транскрипции. Для локального STT
нужен отдельный whisper-сервер (speaches/whisper.cpp) через STT_BACKEND=custom.
"""

import io
import logging

from openai import AsyncOpenAI

from config import STTBackend, settings

log = logging.getLogger(__name__)


def _make_stt_client() -> AsyncOpenAI | None:
    if settings.stt_backend == STTBackend.DISABLED:
        return None
    if settings.stt_backend == STTBackend.CUSTOM:
        return AsyncOpenAI(
            base_url=settings.stt_base_url,
            api_key=settings.openai_api_key or "not-needed",
            timeout=settings.stt_timeout,
        )
    # STTBackend.OPENAI — облачный OpenAI
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.stt_timeout,
    )


_stt_client: AsyncOpenAI | None = _make_stt_client()


async def transcribe(voice_bytes: bytes) -> str:
    """
    Транскрибирует OGG/Opus аудио (из Telegram) в текст.
    Возвращает пустую строку, если распознавание не дало результата.
    Выбрасывает RuntimeError если STT_BACKEND=disabled.
    """
    if _stt_client is None:
        raise RuntimeError("STT отключён (STT_BACKEND=disabled)")

    audio = io.BytesIO(voice_bytes)
    audio.name = "voice.ogg"  # Whisper определяет формат по расширению

    log.debug(
        "STT [%s/%s]: отправляю %d байт",
        settings.stt_backend, settings.stt_model, len(voice_bytes),
    )

    response = await _stt_client.audio.transcriptions.create(
        model=settings.stt_model,
        file=audio,
        language="ru",
    )
    text = (response.text or "").strip()
    log.info("STT: распознано %r", text[:120])
    return text
