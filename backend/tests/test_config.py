from app.core.config import Settings


def test_xkiro_defaults_are_configured() -> None:
    settings = Settings()

    assert settings.xkiro_base_url == "https://api.xkiro.com/v1"
    assert settings.xkiro_model


def test_price_defaults_are_conservative() -> None:
    settings = Settings()

    assert settings.price_min_observations == 3
    assert settings.price_max_observation_age_days == 90
    assert settings.price_max_observations == 2000
    assert settings.price_duplicate_window_minutes == 15
    assert settings.price_seed_prices_path.name == "seed_prices.json"
    assert settings.price_seed_prices_path.parent.name == "data"


def test_postgres_uri_strips_asyncpg_driver() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/scrapsense"
    )

    assert settings.postgres_uri == "postgresql://user:pass@localhost:5432/scrapsense"
