from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.price import PriceEstimate
from app.tools import price_estimator


class FakeSession:
    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False


class FakePriceService:
    def __init__(self, *, session: Any, settings: Any) -> None:
        self.session = session
        self.settings = settings

    async def estimate(
        self,
        *,
        material: str,
        location: str | None = None,
        area: str | None = None,
    ) -> PriceEstimate:
        return PriceEstimate(
            material="plastic",
            material_label="Plastic",
            location=location,
            area=area,
            currency="PKR",
            estimated_price_per_kg=150.0,
            source="local_reports",
            geographic_scope="area",
            observation_count=3,
            local_observation_count=3,
            city_observation_count=3,
            observed_min_price_per_kg=120.0,
            observed_max_price_per_kg=180.0,
            oldest_observation_at=datetime(2026, 10, 24, tzinfo=UTC),
            newest_observation_at=datetime(2026, 10, 25, tzinfo=UTC),
            freshness_days=1.0,
            evidence_quality="medium",
            confidence=0.65,
            message=f"Based on checked reports for {material}.",
            generated_at=datetime(2026, 10, 25, 12, tzinfo=UTC),
        )


class ExplodingPriceService(FakePriceService):
    async def estimate(
        self,
        *,
        material: str,
        location: str | None = None,
        area: str | None = None,
    ) -> PriceEstimate:
        raise SQLAlchemyError("database is down")


async def test_price_tool_uses_the_shared_estimator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(price_estimator, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(price_estimator, "PriceService", FakePriceService)

    result = await price_estimator.estimate_price("plastic", "Multan", "Shah Rizwan")

    assert result["source"] == "local_reports"
    assert result["estimated_price_per_kg"] == 150.0
    assert result["observation_count"] == 3


async def test_price_tool_reports_database_failure_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(price_estimator, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(price_estimator, "PriceService", ExplodingPriceService)

    result = await price_estimator.estimate_price("plastic", "Multan")

    assert result["source"] == "unavailable"
    assert result["estimated_price_per_kg"] is None
    message = result["message"]
    assert isinstance(message, str)
    assert "temporarily unavailable" in message
