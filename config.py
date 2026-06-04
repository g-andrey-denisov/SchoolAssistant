from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMBackend(StrEnum):
    OPENAI = "openai"
    LMSTUDIO = "lmstudio"


class STTBackend(StrEnum):
    OPENAI = "openai"    # облачный OpenAI Whisper
    CUSTOM = "custom"    # OpenAI-совместимый сервер (speaches, whisper.cpp и т.п.)
    DISABLED = "disabled"  # голосовые сообщения отключены


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str
    # Whitelist Telegram user-id (через запятую в .env); пусто = НИКОГО не пускать.
    # Храним как строку, чтобы pydantic-settings не пытался JSON-декодировать
    # сложный тип (set/list) из .env. Парсинг — в свойстве allowed_user_ids ниже.
    allowed_user_ids_raw: str = Field(default="", validation_alias="allowed_user_ids")

    # --- LLM ---
    llm_backend: LLMBackend = LLMBackend.OPENAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    lmstudio_base_url: str = "http://172.16.10.38:1234/v1"
    lmstudio_model: str = "qwen3.5-9b-claude-4.6-highiq-instruct"
    llm_timeout: float = 60.0

    # --- STT (Whisper) ---
    stt_backend: STTBackend = STTBackend.OPENAI
    stt_model: str = "whisper-large-v3"
    stt_timeout: float = 60.0
    # URL для STT_BACKEND=custom (OpenAI-совместимый whisper-сервер)
    stt_base_url: str = ""

    # --- Google Sheets ---
    google_credentials_file: Path = Path("credentials/service_account.json")
    google_spreadsheet_id: str

    sheet_contacts: str = "Контакты"    # ФИО ученика | ДР | ФИО родителя | Телефон | Примечание
    sheet_finances: str = "Финансы"     # ФИО ученика | <по столбцу на каждое событие>

    # --- Логирование ---
    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    log_max_bytes: int = 5 * 1024 * 1024
    log_backup_count: int = 7

    @property
    def allowed_user_ids(self) -> set[int]:
        v = self.allowed_user_ids_raw
        if not v:
            return set()
        return {int(x) for x in v.replace(";", ",").split(",") if x.strip()}


def load_settings() -> Settings:
    return Settings()


settings = load_settings()
