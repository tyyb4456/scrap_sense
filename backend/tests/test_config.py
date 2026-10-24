from app.core.config import Settings


def test_xkiro_defaults_are_configured() -> None:
    settings = Settings()

    assert settings.xkiro_base_url == "https://api.xkiro.com/v1"
    assert settings.xkiro_model


def test_postgres_uri_strips_asyncpg_driver() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/scrapsense"
    )

    assert settings.postgres_uri == "postgresql://user:pass@localhost:5432/scrapsense"
