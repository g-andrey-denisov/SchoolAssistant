"""
STT-клиент: транскрибирует голосовое сообщение через Whisper-эндпоинт.

Локальные серверы (LM Studio и аналоги) требуют JSON + base64-аудио.
OpenAI API работает через SDK (multipart/form-data).
"""

import base64
import io
import logging

import httpx
from openai import AsyncOpenAI

from config import LLMBackend, settings

log = logging.getLogger(__name__)

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.stt_timeout,
        )
    return _openai_client


def _local_stt_config() -> tuple[str, str] | None:
    """Возвращает (base_url, api_key) если используется локальный STT-сервер, иначе None."""
    if settings.stt_base_url:
        return settings.stt_base_url.rstrip("/"), "lm-studio"
    if settings.llm_backend == LLMBackend.LMSTUDIO:
        return settings.lmstudio_base_url.rstrip("/"), "lm-studio"
    return None


async def _transcribe_local(voice_bytes: bytes, base_url: str, api_key: str) -> str:
    """Отправляет аудио как base64 JSON — формат, который принимают локальные серверы."""
    audio_b64 = base64.b64encode(voice_bytes).decode()
    async with httpx.AsyncClient(timeout=settings.stt_timeout) as client:
        resp = await client.post(
            f"{base_url}/audio/transcriptions",
            json={"model": settings.stt_model, "file": audio_b64, "language": "ru"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()


async def _transcribe_openai(voice_bytes: bytes) -> str:
    """Отправляет аудио через OpenAI SDK (multipart/form-data)."""
    audio = io.BytesIO(voice_bytes)
    audio.name = "voice.ogg"
    response = await _get_openai_client().audio.transcriptions.create(
        model=settings.stt_model,
        file=audio,
        language="ru",
    )
    return (response.text or "").strip()


async def transcribe(voice_bytes: bytes) -> str:
    """
    Транскрибирует OGG/Opus аудио (из Telegram) в текст.
    Возвращает пустую строку, если распознавание не дало результата.
    """
    log.debug("STT: отправляю %d байт на транскрипцию (модель=%s)", len(voice_bytes), settings.stt_model)

    local = _local_stt_config()
    if local:
        base_url, api_key = local
        text = await _transcribe_local(voice_bytes, base_url, api_key)
    else:
        text = await _transcribe_openai(voice_bytes)

    log.info("STT: распознано %r", text[:120])
    return text
