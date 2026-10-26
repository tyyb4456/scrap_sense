from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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

    xkiro_api_key: SecretStr | None = None

    xkiro_base_url: str = "https://api.xkiro.com/v1"
    xkiro_model: str = "mistralai/mistral-large-2512"
    
    use_llm_reasoning: bool = False
    anomaly_llm_timeout_seconds: float = Field(default=15.0, gt=0)

    # Anomaly detection. Tier 1 is deterministic and enabled. Tier 2 (ML) stays
    # disabled until there is a documented, sufficiently large real dataset and
    # a trained artifact; see app/services/ml_anomaly.py.
    anomaly_min_sample_size: int = Field(default=5, ge=2)
    anomaly_max_observation_age_days: int = Field(default=90, ge=1)
    anomaly_max_comparisons: int = Field(default=500, ge=1)
    anomaly_mad_z_threshold: float = Field(default=3.5, gt=0)
    anomaly_min_relative_deviation: float = Field(default=0.5, gt=0, lt=10)
    anomaly_zero_mad_min_relative_deviation: float = Field(default=1.0, gt=0, lt=10)
    anomaly_ml_enabled: bool = False
    anomaly_ml_min_reports: int = Field(default=200, ge=1)
    anomaly_ml_artifact_path: Path = (
        BACKEND_DIR / "app" / "ml_artifacts" / "isolation_forest.joblib"
    )

    # Price intelligence. These are conservative defaults, not scientifically
    # validated thresholds. Tune them once real field data volume is known.
    price_min_observations: int = Field(default=3, ge=1)
    price_max_observation_age_days: int = Field(default=90, ge=1)
    price_max_observations: int = Field(default=2000, ge=1)
    price_duplicate_window_minutes: int = Field(default=15, ge=0)
    price_seed_prices_path: Path = BACKEND_DIR / "app" / "data" / "seed_prices.json"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    clerk_secret_key: SecretStr | None = None
    clerk_jwt_key: SecretStr | None = None
    clerk_authorized_parties: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    admin_user_ids: list[str] = Field(default_factory=list)

    @property
    def postgres_uri(self) -> str:
        """Return a Psycopg-compatible URI for LangGraph persistence."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
