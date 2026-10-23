from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "ScrapSense API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://scrapsense:scrapsense@localhost:5432/scrapsense"
    database_echo: bool = False

    ai_model: str = "openai:gpt-4.1-mini"

    @field_validator("ai_model")
    @classmethod
    def validate_ai_model(cls, value: str) -> str:
        if ":" not in value:
            raise ValueError("ai_model must use the provider:model format")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
