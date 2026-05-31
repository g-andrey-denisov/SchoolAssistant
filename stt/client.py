"""
STT-клиент: транскрибирует голосовое сообщение через Whisper-эндпоинт.

Стратегия для локальных серверов:
  1. Пробуем multipart/form-data (стандарт OpenAI, работает когда модель загружена).
  2. Если 415 — fallback на JSON+base64 (некоторые версии LM Studio без модели).
OpenAI API всегда использует multipart через SDK.
"""

import base64
import io
import logging

import httpx
import openai
from openai import AsyncOpenAI

from config import LLMBackend, settings

log = logging.getLogger(__name__)


def _local_stt_config() -> tuple[str, str] | None:
    """Возвращает (base_url, api_key) для локального STT-сервера, иначе None."""
    if settings.stt_base_url:
        return settings.stt_base_url.rstrip("/"), "lm-studio"
    if settings.llm_backend == LLMBackend.LMSTUDIO:
        return settings.lmstudio_base_url.rstrip("/"), "lm-studio"
    return None


async def _transcribe_multipart(base_url: str | None, api_key: str, voice_bytes: bytes) -> str:
    """Multipart/form-data через OpenAI SDK — стандартный OpenAI-совместимый формат."""
    kwargs = {"api_key": api_key, "timeout": settings.stt_timeout}
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)
    audio = io.BytesIO(voice_bytes)
    audio.name = "voice.ogg"
    response = await client.audio.transcriptions.create(
        model=settings.stt_model,
        file=audio,
        language="ru",
    )
    return (response.text or "").strip()


async def _transcribe_json_b64(base_url: str, api_key: str, voice_bytes: bytes) -> str:
    """JSON + base64 — fallback для серверов, отклоняющих multipart."""
    audio_b64 = base64.b64encode(voice_bytes).decode()
    async with httpx.AsyncClient(timeout=settings.stt_timeout) as client:
        resp = await client.post(
            f"{base_url}/audio/transcriptions",
            json={"model": settings.stt_model, "file": audio_b64, "language": "ru"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()


async def transcribe(voice_bytes: bytes) -> str:
    """
    Транскрибирует OGG/Opus аудио (из Telegram) в текст.
    Возвращает пустую строку, если распознавание не дало результата.
    """
    log.debug("STT: отправляю %d байт на транскрипцию (модель=%s)", len(voice_bytes), settings.stt_model)

    local = _local_stt_config()

    if local:
        base_url, api_key = local
        try:
            text = await _transcribe_multipart(base_url, api_key, voice_bytes)
        except openai.APIStatusError as exc:
            if exc.status_code == 415:
                log.warning("STT: multipart отклонён (415), пробую JSON+base64")
                text = await _transcribe_json_b64(base_url, api_key, voice_bytes)
            else:
                raise
    else:
        text = await _transcribe_multipart(None, settings.openai_api_key, voice_bytes)

    log.info("STT: распознано %r", text[:120])
    return text
