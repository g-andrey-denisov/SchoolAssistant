"""
STT-клиент: транскрибирует голосовое сообщение через Whisper-эндпоинт LM Studio.

LM Studio поднимает /v1/audio/transcriptions при загруженной Whisper-модели.
Используем тот же base_url, что и LLM-клиент.
"""

import io
import logging

from openai import AsyncOpenAI

from config import LLMBackend, settings

log = logging.getLogger(__name__)


def _make_stt_client() -> AsyncOpenAI:
    # Явный STT_BASE_URL имеет наивысший приоритет (любой OpenAI-совместимый сервер)
    if settings.stt_base_url:
        return AsyncOpenAI(
            base_url=settings.stt_base_url,
            api_key="lm-studio",
            timeout=settings.stt_timeout,
        )
    if settings.llm_backend == LLMBackend.LMSTUDIO:
        return AsyncOpenAI(
            base_url=settings.lmstudio_base_url,
            api_key="lm-studio",
            timeout=settings.stt_timeout,
        )
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
