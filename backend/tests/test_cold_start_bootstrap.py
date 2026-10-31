"""Cold-start bootstrap scenarios for Tier 1 evidence.

These tests use the real PostgreSQL test database. Trusted reports inserted
through ``save_report(..., pass)`` represent pre-existing, independently
verified history; they are not produced by the cold-start intake path. All
prices are artificial test fixtures inside an isolated city/material namespace.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.report import Report
from app.schemas.report import AnomalyVerdict, FinalReport, ReportDraft
from app.services.anomaly_detection import evaluate_report_statistical_with_session
from app.services.prices import PriceService
from app.services.report_reevaluation import (
    reevaluate_pending_report,
    reevaluate_pending_reports,
)
from app.services.reports import REPORT_STATUS_ACCEPTED, save_report


def _draft(
    *,
    city: str,
    area: str | None,
    price: str,
    material: str = "plastic",
    observed_at: datetime | None = None,
) -> ReportDraft:
    return ReportDraft(
        material=material,
        price_per_kg=Decimal(price),
        quantity_kg=Decimal("2"),
        currency="PKR",
        unit="kg",
        city=city,
        area=area,
        observed_at=observed_at or (datetime.now(UTC) - timedelta(days=1)),
        confidence=0.8,
    )


def _pass_verdict(reason: str = "Price is within the comparable range. fixture") -> AnomalyVerdict:
    return AnomalyVerdict(
        is_anomalous=False,
        reason=reason,
        method="mad",
        confidence=0.6,
        outcome="pass",
    )


async def _evaluate(
    draft: ReportDraft,
    *,
    settings: Settings | None = None,
) -> AnomalyVerdict:
    async with SessionLocal() as session:
        return await evaluate_report_statistical_with_session(
            draft,
            session=session,
            settings=settings or Settings(),
        )


async def _intake(
    draft: ReportDraft,
    *,
    picker_id: str,
    settings: Settings | None = None,
) -> tuple[AnomalyVerdict, FinalReport]:
    verdict = await _evaluate(draft, settings=settings)
    report = await save_report(
        picker_id=picker_id,
        raw_text=f"fixture raw picker message from {picker_id}",
        draft=draft,
        verdict=verdict,
    )
    return verdict, report


async def _trusted(
    draft: ReportDraft,
    *,
    picker_id: str,
) -> FinalReport:
    return await save_report(
        picker_id=picker_id,
        raw_text=f"fixture trusted history from {picker_id}",
        draft=draft,
        verdict=_pass_verdict(),
    )


async def _delete(report_ids: Sequence[UUID]) -> None:
    if not report_ids:
        return
    async with SessionLocal() as session:
        await session.execute(delete(Report).where(Report.id.in_(report_ids)))
        await session.commit()


async def _status(report_id: UUID) -> Report | None:
    async with SessionLocal() as session:
        return await session.get(Report, report_id)


async def _batch_results(report_ids: set[UUID]):
    results = await reevaluate_pending_reports(settings=Settings(), limit=10000)
    return [result for result in results if result.report_id in report_ids]


async def test_new_material_and_city_cold_start_stays_pending(postgres_db: None) -> None:
    """Scenario A/B/G: no trusted history means every report stays pending."""
    unique = uuid4().hex
    city = f"Cold Bootstrap City {unique}"
    material = "glass"
    created: list[UUID] = []
    try:
        for index in range(6):
            verdict, report = await _intake(
                _draft(city=city, area=None, price=str(100 + index), material=material),
                picker_id=f"cold-{unique}-{index}",
            )
            created.append(report.id)
            assert verdict.outcome == "insufficient_evidence"
            assert verdict.sample_size == 0
            assert report.status == "pending_evidence"
            assert report.is_anomalous is False

        first_batch = await _batch_results(set(created))
        assert len(first_batch) == len(created)
        assert all(result.status == "pending_evidence" for result in first_batch)

        second_batch = await _batch_results(set(created))
        assert len(second_batch) == len(created)
        assert all(result.status == "pending_evidence" for result in second_batch)

        async with SessionLocal() as session:
            accepted = await session.scalar(
                select(func.count(Report.id)).where(
                    Report.city == city,
                    Report.material == material,
                    Report.status == REPORT_STATUS_ACCEPTED,
                )
            )
        assert accepted == 0

        async with SessionLocal() as session:
            estimate = await PriceService(
                session=session,
                settings=Settings(price_min_observations=1),
            ).estimate(material=material, location=city, area=None)
        assert estimate.source == "unavailable"
        assert estimate.estimated_price_per_kg is None
    finally:
        await _delete(created)


async def test_trusted_history_in_another_city_does_not_unlock_a_new_city(
    postgres_db: None,
) -> None:
    """Scenario E: comparison is strictly local; national/city mixing is absent."""
    unique = uuid4().hex
    evidence_city = f"Evidence City {unique}"
    new_city = f"New City {unique}"
    created: list[UUID] = []
    try:
        for index in range(5):
            report = await _trusted(
                _draft(city=evidence_city, area=None, price=str(100 + index)),
                picker_id=f"other-city-{unique}-{index}",
            )
            created.append(report.id)

        verdict, pending = await _intake(
            _draft(city=new_city, area=None, price="102"),
            picker_id=f"new-city-{unique}",
        )
        created.append(pending.id)
        assert verdict.outcome == "insufficient_evidence"
        assert verdict.sample_size == 0
        assert pending.status == "pending_evidence"

        results = await _batch_results({pending.id})
        assert len(results) == 1
        assert results[0].status == "pending_evidence"

        stored = await _status(pending.id)
        assert stored is not None
        assert stored.status == "pending_evidence"
        assert stored.anomaly_outcome == "insufficient_evidence"
    finally:
        await _delete(created)


async def test_city_level_trusted_history_can_promote_a_pending_area(
    postgres_db: None,
) -> None:
    """Scenario C/D: the same-city baseline is used when the area is sparse."""
    unique = uuid4().hex
    city = f"City Scope City {unique}"
    evidence_area = f"Evidence Area {unique}"
    pending_area = f"Pending Area {unique}"
    created: list[UUID] = []
    try:
        verdict, pending = await _intake(
            _draft(city=city, area=pending_area, price="102"),
            picker_id=f"city-scope-pending-{unique}",
        )
        created.append(pending.id)
        assert verdict.outcome == "insufficient_evidence"
        assert pending.status == "pending_evidence"

        for index in range(5):
            report = await _trusted(
                _draft(
                    city=city,
                    area=evidence_area,
                    price=str(100 + index * 2),
                ),
                picker_id=f"city-scope-evidence-{unique}-{index}",
            )
            created.append(report.id)

        async with SessionLocal() as session:
            result = await reevaluate_pending_report(
                session,
                report_id=pending.id,
                settings=Settings(),
            )

        assert result is not None
        assert result.transitioned is True
        assert result.status == "accepted"
        assert result.outcome == "pass"

        stored = await _status(pending.id)
        assert stored is not None
        assert stored.status == "accepted"
        assert stored.anomaly_outcome == "pass"
        assert "city-level" in stored.anomaly_reason
        assert stored.is_anomalous is False
    finally:
        await _delete(created)


async def test_pending_report_is_excluded_from_its_own_comparison(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Self Compare City {unique}"
    created: list[UUID] = []
    try:
        draft = _draft(city=city, area=None, price="150")
        verdict, pending = await _intake(
            draft,
            picker_id=f"self-compare-{unique}",
        )
        created.append(pending.id)
        assert verdict.outcome == "insufficient_evidence"
        assert pending.status == "pending_evidence"

        second = await _evaluate(draft)
        assert second.outcome == "insufficient_evidence"
        assert second.sample_size == 0

        async with SessionLocal() as session:
            result = await reevaluate_pending_report(
                session,
                report_id=pending.id,
                settings=Settings(),
            )
        assert result is not None
        assert result.status == "pending_evidence"
    finally:
        await _delete(created)


async def test_verified_seed_price_is_pricing_evidence_not_tier1_evidence(
    postgres_db: None,
    tmp_path: Path,
) -> None:
    """Scenario F: an audited seed reference cannot create a statistical pass."""
    unique = uuid4().hex
    city = f"Seed Only City {unique}"
    seed_path = tmp_path / "seed_prices.json"
    seed_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "material": "plastic",
                        "city": city,
                        "price_per_kg": 180,
                        "currency": "PKR",
                        "unit": "kg",
                        "source": "fixture audited field visit, not live data",
                        "collector": "fixture collector",
                        "collected_at": date.today().isoformat(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(price_seed_prices_path=seed_path)
    created: list[UUID] = []
    try:
        draft = _draft(city=city, area=None, price="180")
        verdict, pending = await _intake(
            draft,
            picker_id=f"seed-only-{unique}",
            settings=settings,
        )
        created.append(pending.id)
        assert verdict.outcome == "insufficient_evidence"
        assert verdict.sample_size == 0
        assert pending.status == "pending_evidence"

        async with SessionLocal() as session:
            estimate = await PriceService(
                session=session,
                settings=settings,
            ).estimate(material="plastic", location=city, area=None)
        assert estimate.source == "seed_data"
        assert estimate.geographic_scope == "city"
        assert estimate.estimated_price_per_kg == 180.0
        assert estimate.seed_source == "fixture audited field visit, not live data"

        stored = await _status(pending.id)
        assert stored is not None
        assert stored.status == "pending_evidence"
        assert stored.anomaly_outcome == "insufficient_evidence"
    finally:
        await _delete(created)


async def test_batch_reevaluation_is_order_independent_and_idempotent(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    unlockable_city = f"Batch Unlock City {unique}"
    cold_city = f"Batch Cold City {unique}"
    unlockable_pending: list[UUID] = []
    cold_pending: list[UUID] = []
    created: list[UUID] = []
    try:
        for index in range(2):
            _, report = await _intake(
                _draft(city=unlockable_city, area=None, price="102"),
                picker_id=f"batch-unlock-{unique}-{index}",
            )
            unlockable_pending.append(report.id)
            created.append(report.id)

        for index in range(2):
            _, report = await _intake(
                _draft(city=cold_city, area=None, price="102"),
                picker_id=f"batch-cold-{unique}-{index}",
            )
            cold_pending.append(report.id)
            created.append(report.id)

        for index in range(5):
            report = await _trusted(
                _draft(city=unlockable_city, area=None, price=str(100 + index)),
                picker_id=f"batch-evidence-{unique}-{index}",
            )
            created.append(report.id)

        first = await _batch_results(set(unlockable_pending) | set(cold_pending))
        by_id = {result.report_id: result for result in first}
        assert all(by_id[report_id].status == "accepted" for report_id in unlockable_pending)
        assert all(
            by_id[report_id].status == "pending_evidence" for report_id in cold_pending
        )

        second = await _batch_results(set(unlockable_pending) | set(cold_pending))
        assert all(result.report_id in cold_pending for result in second)
        assert all(result.status == "pending_evidence" for result in second)

        async with SessionLocal() as session:
            for report_id in unlockable_pending:
                count = await session.scalar(
                    select(func.count(Report.id)).where(Report.id == report_id)
                )
                assert count == 1
            for report_id in cold_pending:
                stored = await session.get(Report, report_id)
                assert stored is not None
                assert stored.status == "pending_evidence"
    finally:
        await _delete(created)
