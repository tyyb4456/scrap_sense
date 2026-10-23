import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_ai_model_requires_provider_prefix() -> None:
    with pytest.raises(ValidationError):
        Settings(ai_model="gpt-4.1-mini")


def test_ai_model_accepts_provider_model() -> None:
    settings = Settings(ai_model="openai:gpt-4.1-mini")

    assert settings.ai_model == "openai:gpt-4.1-mini"


def test_postgres_uri_strips_asyncpg_driver() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/scrapsense"
    )

    assert settings.postgres_uri == "postgresql://user:pass@localhost:5432/scrapsense"
