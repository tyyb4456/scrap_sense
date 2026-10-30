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
from app.schemas.report import AnomalyVerdict, ReportDraft
from app.services.prices import PriceService
from app.services.reports import save_report


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
    city: str | None,
    area: str,
    price: str,
    picker_id: str,
    created_at: datetime,
    status: str = "accepted",
    is_anomalous: bool = False,
    observed_at: datetime | None = None,
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
        observed_at=observed_at,
        confidence=0.9,
        is_anomalous=is_anomalous,
        anomaly_reason=(
            "Price is a statistical outlier."
            if is_anomalous
            else "No anomaly detected."
        ),
        anomaly_method="mad",
        status=status,
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


async def test_postgres_suspicious_reports_do_not_influence_the_estimate() -> None:
    await _require_postgres()
    unique = uuid.uuid4().hex
    city = f"Review City {unique}"
    area = f"Review Area {unique}"
    now = datetime.now(UTC)

    async with SessionLocal() as session:
        try:
            session.add_all(
                [
                    report(
                        city=city,
                        area=area,
                        price="100",
                        picker_id=f"review-picker-{unique}-1",
                        created_at=now - timedelta(days=1),
                    ),
                    report(
                        city=city,
                        area=area,
                        price="200",
                        picker_id=f"review-picker-{unique}-2",
                        created_at=now - timedelta(days=1),
                    ),
                    report(
                        city=city,
                        area=area,
                        price="5000",
                        picker_id=f"review-picker-{unique}-3",
                        created_at=now - timedelta(days=1),
                        status="flagged",
                        is_anomalous=True,
                    ),
                    report(
                        city=city,
                        area=area,
                        price="9000",
                        picker_id=f"review-picker-{unique}-4",
                        created_at=now - timedelta(days=1),
                        is_anomalous=True,
                    ),
                    report(
                        city=city,
                        area=area,
                        price="8000",
                        picker_id=f"review-picker-{unique}-5",
                        created_at=now - timedelta(days=1),
                        status="rejected",
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
            assert result.observation_count == 2
            assert result.observed_max_price_per_kg == 200.0
        finally:
            await session.rollback()
            await engine.dispose()


async def test_postgres_observation_age_uses_reported_sale_time() -> None:
    await _require_postgres()
    unique = uuid.uuid4().hex
    city = f"Timestamp City {unique}"
    now = datetime.now(UTC)

    async with SessionLocal() as session:
        try:
            session.add_all(
                [
                    report(
                        city=city,
                        area="Area",
                        price="100",
                        picker_id=f"time-picker-{unique}-1",
                        created_at=now,
                        observed_at=now - timedelta(days=200),
                    ),
                    report(
                        city=city,
                        area="Area",
                        price="200",
                        picker_id=f"time-picker-{unique}-2",
                        created_at=now,
                        observed_at=now - timedelta(days=200),
                    ),
                ]
            )
            await session.flush()

            service = PriceService(
                session=session,
                settings=Settings(price_min_observations=2),
            )
            result = await service.estimate(material="plastic", location=city)

            assert result.source == "unavailable"
            assert result.estimated_price_per_kg is None
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

async def test_postgres_cityless_historical_reports_are_excluded_from_estimates() -> None:
    await _require_postgres()
    unique = uuid.uuid4().hex
    city = f"Historical City {unique}"
    area = f"Historical Area {unique}"
    now = datetime.now(UTC)

    async with SessionLocal() as session:
        try:
            null_city = report(
                city=None,
                area=area,
                price="9999",
                picker_id=f"history-picker-{unique}-1",
                created_at=now - timedelta(days=1),
            )
            blank_city = report(
                city="",
                area=area,
                price="8888",
                picker_id=f"history-picker-{unique}-2",
                created_at=now - timedelta(days=1),
            )
            session.add_all(
                [
                    null_city,
                    blank_city,
                    report(
                        city=city,
                        area=area,
                        price="100",
                        picker_id=f"history-picker-{unique}-3",
                        created_at=now - timedelta(days=1),
                    ),
                    report(
                        city=city,
                        area=area,
                        price="200",
                        picker_id=f"history-picker-{unique}-4",
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
                area=area,
            )

            assert result.source == "local_reports"
            assert result.estimated_price_per_kg == 150.0
            assert result.observation_count == 2
            assert result.observed_max_price_per_kg == 200.0

            # Historical rows are not rewritten by the price read path.
            assert null_city.city is None
            assert blank_city.city == ""
            assert null_city.status == "accepted"
            assert blank_city.status == "accepted"
        finally:
            await session.rollback()
            await engine.dispose()


async def test_postgres_save_report_persists_a_suspicious_report_as_flagged() -> None:
    await _require_postgres()
    unique = uuid.uuid4().hex
    city = f"Persist City {unique}"
    now = datetime.now(UTC)
    draft = ReportDraft(
        material="plastic",
        price_per_kg=Decimal("9999"),
        quantity_kg=Decimal("2"),
        currency="PKR",
        unit="kg",
        city=city,
        area=f"Persist Area {unique}",
        observed_at=now,
    )
    verdict = AnomalyVerdict(
        is_anomalous=True,
        reason="Price is a statistical outlier.",
        method="mad",
        confidence=0.75,
        outcome="suspicious",
        sample_size=5,
    )

    saved = await save_report(
        picker_id=f"persist-picker-{unique}",
        raw_text="integration fixture",
        draft=draft,
        verdict=verdict,
    )
    try:
        async with SessionLocal() as session:
            stored = await session.get(Report, saved.id)
            assert stored is not None
            assert stored.status == "flagged"
            assert stored.is_anomalous is True
            assert stored.observed_at is not None
            assert stored.reviewed_at is None

            service = PriceService(
                session=session,
                settings=Settings(price_min_observations=1),
            )
            estimate = await service.estimate(material="plastic", location=city)
            assert estimate.source == "unavailable"
    finally:
        async with SessionLocal() as session:
            stored = await session.get(Report, saved.id)
            if stored is not None:
                await session.delete(stored)
                await session.commit()
        await engine.dispose()
