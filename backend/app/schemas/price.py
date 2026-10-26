"""Schemas for evidence-based scrap price estimates and seed-price files."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PriceSource = Literal["local_reports", "city_reports", "seed_data", "unavailable"]
GeographicScope = Literal["area", "city", "national", "none"]
EvidenceQuality = Literal["high", "medium", "low", "none"]


class PriceEstimate(BaseModel):
    """Stable public response for a material price estimate."""

    material: str
    material_label: str
    location: str | None
    area: str | None
    currency: str
    unit: Literal["kg"] = "kg"

    estimated_price_per_kg: float | None
    source: PriceSource
    geographic_scope: GeographicScope

    observation_count: int = Field(ge=0)
    local_observation_count: int = Field(ge=0)
    city_observation_count: int = Field(ge=0)
    observed_min_price_per_kg: float | None = None
    observed_max_price_per_kg: float | None = None

    oldest_observation_at: datetime | None = None
    newest_observation_at: datetime | None = None
    freshness_days: float | None = None

    evidence_quality: EvidenceQuality
    confidence: float = Field(ge=0.0, le=1.0)

    seed_source: str | None = None
    seed_collected_at: date | None = None

    message: str
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime


class SeedPriceEntry(BaseModel):
    """One audited seed reference. Values must come from a real collection."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    material: str = Field(min_length=1, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    price_per_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="PKR", min_length=3, max_length=3)
    unit: Literal["kg"] = "kg"
    source: str = Field(min_length=1, max_length=300)
    collector: str | None = Field(default=None, max_length=100)
    collected_at: date


class SeedPriceFile(BaseModel):
    """Top-level shape of ``app/data/seed_prices.json``."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1
    notes: str | None = None
    entries: list[SeedPriceEntry] = Field(default_factory=list)
