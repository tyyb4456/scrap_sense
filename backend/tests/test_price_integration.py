"""Genuine PostgreSQL integration coverage for the price read path.

These tests run only when the configured PostgreSQL database is reachable and
the ``reports`` table exists. They insert rows inside a transaction and roll it
back, so they do not change existing development data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import SessionLocal, engine
from app.models.report import Report
from app.services.prices import PriceService


async def _require_postgres() -> None:
    # Each pytest-asyncio test gets a fresh event loop, so discard pooled
    # asyncpg connections created on a previous loop before connecting again.
    await engine.dispose()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            has_reports = await connection.scalar(text("SELECT to_regclass('public.reports')"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(
            "PostgreSQL integration test unavailable. Start it with "
            f"`docker compose up -d db` and run `uv run alembic upgrade head`: {exc}"
        )
    if has_reports is None:  # pragma: no cover - environment dependent
        pytest.skip(
            "The reports table is missing. Run `uv run alembic upgrade head` first."
        )


def report(
    *,
    city: str,
    area: str,
    price: str,
    picker_id: str,
    created_at: datetime,
) -> Report:
    return Report(
        picker_id=picker_id,
        raw_text="integration fixture",
        material="plastic",
        price_per_kg=Decimal(price),
        quantity_kg=Decimal("2"),
        currency="PKR",
        city=city,
        area=area,
        confidence=0.9,
        is_anomalous=False,
        anomaly_reason="Not enough data to evaluate.",
        anomaly_method="deterministic",
        status="accepted",
        created_at=created_at,
    )


async def test_postgres_repository_and_local_estimate() -> None:
    await _require_postgres()
    unique = uuid.uuid4().hex
    city = f"Test City {unique}"
    area = f"Test Area {unique}"
    now = datetime.now(UTC)

    async with SessionLocal() as session:
        try:
            session.add_all(
                [
                    report(
                        city=city,
                        area=area,
                        price="100",
                        picker_id=f"test-picker-{unique}-1",
                        created_at=now - timedelta(days=1),
                    ),
                    report(
                        city=city,
                        area=area,
                        price="200",
                        picker_id=f"test-picker-{unique}-2",
                        created_at=now - timedelta(hours=4),
                    ),
                ]
            )
            await session.flush()

            service = PriceService(
                session=session,
                settings=Settings(price_min_observations=2),
            )
            result = await service.estimate(
                material="plastic",
                location=city,
                area=area,
            )

            assert result.source == "local_reports"
            assert result.estimated_price_per_kg == 150.0
            assert result.observed_min_price_per_kg == 100.0
            assert result.observed_max_price_per_kg == 200.0
            assert result.local_observation_count == 2
            assert result.city_observation_count == 2
            assert result.freshness_days is not None
            assert result.freshness_days < 2
        finally:
            await session.rollback()
            await engine.dispose()


async def test_postgres_repository_falls_back_to_city_evidence() -> None:
    await _require_postgres()
    unique = uuid.uuid4().hex
    city = f"Fallback City {unique}"
    requested_area = f"Small Area {unique}"
    other_area = f"Other Area {unique}"
    now = datetime.now(UTC)

    async with SessionLocal() as session:
        try:
            session.add_all(
                [
                    report(
                        city=city,
                        area=requested_area,
                        price="100",
                        picker_id=f"fallback-picker-{unique}-1",
                        created_at=now - timedelta(days=1),
                    ),
                    report(
                        city=city,
                        area=other_area,
                        price="200",
                        picker_id=f"fallback-picker-{unique}-2",
                        created_at=now - timedelta(days=1),
                    ),
                    report(
                        city=city,
                        area=other_area,
                        price="300",
                        picker_id=f"fallback-picker-{unique}-3",
                        created_at=now - timedelta(days=1),
                    ),
                ]
            )
            await session.flush()

            service = PriceService(
                session=session,
                settings=Settings(price_min_observations=2),
            )
            result = await service.estimate(
                material="plastic",
                location=city,
                area=requested_area,
            )

            assert result.source == "city_reports"
            assert result.geographic_scope == "city"
            assert result.estimated_price_per_kg == 200.0
            assert result.local_observation_count == 1
            assert result.city_observation_count == 3
        finally:
            await session.rollback()
            await engine.dispose()
