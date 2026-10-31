"""Cold-start intake, trusted-evidence isolation, and re-evaluation coverage."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.report import Report
from app.schemas.report import AnomalyVerdict, FinalReport, ReportDraft
from app.services import report_reevaluation as reevaluation_module
from app.services.anomaly_detection import AnomalyPolicy, evaluate_statistical_anomaly
from app.services.price_aggregation import PriceObservation, eligibility_reason
from app.services.prices import PriceService
from app.services.report_reevaluation import (
    reevaluate_pending_report,
    reevaluate_pending_reports,
)
from app.services.reports import (
    fetch_comparable_reports,
    save_report,
)


def _draft(
    *,
    city: str,
    area: str | None,
    price: str,
    observed_at: datetime | None = None,
    picker_id: str = "picker",
) -> ReportDraft:
    return ReportDraft(
        material="plastic",
        price_per_kg=Decimal(price),
        quantity_kg=Decimal("2"),
        currency="PKR",
        unit="kg",
        city=city,
        area=area,
        observed_at=observed_at or (datetime.now(UTC) - timedelta(days=1)),
        confidence=0.8,
    )


def _verdict(outcome: str, *, is_anomalous: bool = False) -> AnomalyVerdict:
    return AnomalyVerdict(
        is_anomalous=is_anomalous,
        reason=f"fixture outcome {outcome}",
        method="mad",
        confidence=0.6,
        outcome=outcome,  # type: ignore[arg-type]
    )


async def _persist(
    *,
    city: str,
    area: str | None,
    price: str,
    outcome: str,
    raw_text: str = "fixture raw picker message",
    picker_id: str = "picker-fixture",
    observed_at: datetime | None = None,
) -> FinalReport:
    return await save_report(
        picker_id=picker_id,
        raw_text=raw_text,
        draft=_draft(
            city=city,
            area=area,
            price=price,
            observed_at=observed_at,
            picker_id=picker_id,
        ),
        verdict=_verdict(outcome, is_anomalous=outcome == "suspicious"),
    )


async def _delete(report_ids: Sequence[UUID]) -> None:
    if not report_ids:
        return
    async with SessionLocal() as session:
        await session.execute(delete(Report).where(Report.id.in_(report_ids)))
        await session.commit()


async def _estimate(
    *,
    city: str,
    area: str | None,
    min_observations: int = 2,
):
    async with SessionLocal() as session:
        service = PriceService(
            session=session,
            settings=Settings(price_min_observations=min_observations),
        )
        return await service.estimate(material="plastic", location=city, area=area)


def _observation(
    *,
    price: str = "100",
    outcome: str = "pass",
    status: str = "accepted",
    is_anomalous: bool = False,
) -> PriceObservation:
    return PriceObservation(
        report_id=uuid4(),
        picker_id=f"picker-{uuid4()}",
        material="plastic",
        price_per_kg=Decimal(price),
        quantity_kg=Decimal("2"),
        currency="PKR",
        city="Multan",
        area="Area",
        observed_at=datetime.now(UTC) - timedelta(days=1),
        status=status,
        is_anomalous=is_anomalous,
        anomaly_outcome=outcome,
    )


def test_missing_tier1_outcome_is_not_a_pass() -> None:
    with pytest.raises(ValueError):
        AnomalyVerdict(  # type: ignore[call-arg]
            is_anomalous=False,
            reason="no outcome",
            method="mad",
            confidence=0.0,
        )


def test_unknown_and_pending_observations_are_not_pricing_evidence() -> None:
    assert eligibility_reason(_observation(outcome="unknown")) == "anomaly_outcome:unknown"
    assert (
        eligibility_reason(
            _observation(status="pending_evidence", outcome="insufficient_evidence")
        )
        == "status:pending_evidence"
    )


def test_pending_observations_do_not_enter_statistical_baselines() -> None:
    pending = [
        _observation(status="pending_evidence", outcome="insufficient_evidence")
        for _ in range(10)
    ]

    verdict = evaluate_statistical_anomaly(
        material="plastic",
        price_per_kg=Decimal("100"),
        currency="PKR",
        city="Multan",
        area="Area",
        unit="kg",
        observations=pending,
        now=datetime.now(UTC),
        policy=AnomalyPolicy(),
    )

    assert verdict.outcome == "insufficient_evidence"
    assert verdict.sample_size == 0


async def test_pending_intake_preserves_provenance_and_stays_out_of_pricing(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Cold Start City {unique}"
    area = f"Cold Start Area {unique}"
    raw_text = f"picker said: sold 2kg plastic at 150 in {city}"
    created: list[UUID] = []
    try:
        pending = await _persist(
            city=city,
            area=area,
            price="150",
            outcome="insufficient_evidence",
            raw_text=raw_text,
            picker_id=f"clerk-sub-{unique}",
        )
        created.append(pending.id)

        async with SessionLocal() as session:
            stored = await session.get(Report, pending.id)
            assert stored is not None
            assert stored.status == "pending_evidence"
            assert stored.is_anomalous is False
            assert stored.anomaly_outcome == "insufficient_evidence"
            assert stored.raw_text == raw_text
            assert stored.picker_id == f"clerk-sub-{unique}"

        estimate = await _estimate(city=city, area=area, min_observations=1)
        assert estimate.source == "unavailable"
        assert estimate.estimated_price_per_kg is None
    finally:
        await _delete(created)


async def test_pending_and_legacy_unknown_reports_are_not_baseline_evidence(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Baseline City {unique}"
    area = f"Baseline Area {unique}"
    created: list[UUID] = []
    try:
        verified = [
            await _persist(
                city=city,
                area=area,
                price=str(100 + index),
                outcome="pass",
                picker_id=f"verified-{unique}-{index}",
            )
            for index in range(5)
        ]
        created.extend(report.id for report in verified)
        pending = await _persist(
            city=city,
            area=area,
            price="9999",
            outcome="insufficient_evidence",
            picker_id=f"pending-{unique}",
        )
        created.append(pending.id)
        flagged = await _persist(
            city=city,
            area=area,
            price="8888",
            outcome="suspicious",
            picker_id=f"flagged-{unique}",
        )
        created.append(flagged.id)

        async with SessionLocal() as session:
            legacy = Report(
                picker_id=f"legacy-{unique}",
                raw_text="legacy accepted row",
                material="plastic",
                price_per_kg=Decimal("7777"),
                quantity_kg=Decimal("2"),
                currency="PKR",
                city=city,
                area=area,
                observed_at=datetime.now(UTC) - timedelta(days=1),
                confidence=0.8,
                is_anomalous=False,
                anomaly_reason="legacy reason",
                anomaly_method="mad",
                anomaly_outcome="unknown",
                status="accepted",
            )
            session.add(legacy)
            await session.commit()
            await session.refresh(legacy)
            created.append(legacy.id)

            comparable = await fetch_comparable_reports(
                session,
                material_aliases={"plastic"},
                city=city.lower(),
                currency="PKR",
                since=datetime.now(UTC) - timedelta(days=90),
                limit=100,
            )

        comparable_ids = {report.id for report in comparable}
        assert comparable_ids == {report.id for report in verified}
        assert pending.id not in comparable_ids
        assert flagged.id not in comparable_ids
        assert legacy.id not in comparable_ids
    finally:
        await _delete(created)


async def test_pending_reports_do_not_affect_local_or_city_estimates(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Estimate City {unique}"
    area = f"Estimate Area {unique}"
    other_area = f"Other Area {unique}"
    created: list[UUID] = []
    try:
        accepted_a = await _persist(
            city=city,
            area=area,
            price="100",
            outcome="pass",
            picker_id=f"estimate-{unique}-1",
        )
        accepted_b = await _persist(
            city=city,
            area=area,
            price="200",
            outcome="pass",
            picker_id=f"estimate-{unique}-2",
        )
        created.extend([accepted_a.id, accepted_b.id])
        pending_local = await _persist(
            city=city,
            area=area,
            price="9000",
            outcome="insufficient_evidence",
            picker_id=f"estimate-{unique}-3",
        )
        pending_other = await _persist(
            city=city,
            area=other_area,
            price="8000",
            outcome="insufficient_evidence",
            picker_id=f"estimate-{unique}-4",
        )
        created.extend([pending_local.id, pending_other.id])

        local = await _estimate(city=city, area=area)
        assert local.source == "local_reports"
        assert local.observation_count == 2
        assert local.estimated_price_per_kg == 150.0

        city_level = await _estimate(city=city, area=other_area)
        assert city_level.source == "city_reports"
        assert city_level.observation_count == 2
        assert city_level.estimated_price_per_kg == 150.0
    finally:
        await _delete(created)


async def test_unknown_outcome_is_excluded_from_pricing(postgres_db: None) -> None:
    unique = uuid4().hex
    city = f"Unknown City {unique}"
    created: list[UUID] = []
    try:
        async with SessionLocal() as session:
            legacy = Report(
                picker_id=f"unknown-{unique}",
                raw_text="legacy accepted row",
                material="plastic",
                price_per_kg=Decimal("100"),
                quantity_kg=Decimal("2"),
                currency="PKR",
                city=city,
                area=None,
                observed_at=datetime.now(UTC) - timedelta(days=1),
                confidence=0.8,
                is_anomalous=False,
                anomaly_reason="legacy reason",
                anomaly_method="mad",
                anomaly_outcome="unknown",
                status="accepted",
            )
            session.add(legacy)
            await session.commit()
            await session.refresh(legacy)
            created.append(legacy.id)

        estimate = await _estimate(city=city, area=None, min_observations=1)
        assert estimate.source == "unavailable"
        assert estimate.estimated_price_per_kg is None
    finally:
        await _delete(created)


async def test_reevaluation_keeps_pending_when_evidence_is_still_insufficient(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Still Pending City {unique}"
    created: list[UUID] = []
    try:
        pending = await _persist(
            city=city,
            area=None,
            price="150",
            outcome="insufficient_evidence",
            picker_id=f"still-pending-{unique}",
        )
        created.append(pending.id)

        async with SessionLocal() as session:
            result = await reevaluate_pending_report(
                session,
                report_id=pending.id,
                settings=Settings(),
            )

        assert result is not None
        assert result.transitioned is True
        assert result.status == "pending_evidence"
        async with SessionLocal() as session:
            stored = await session.get(Report, pending.id)
            assert stored is not None
            assert stored.status == "pending_evidence"
            assert stored.anomaly_outcome == "insufficient_evidence"
    finally:
        await _delete(created)


async def test_reevaluation_promotes_pending_after_normal_evidence_arrives(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Promote City {unique}"
    area = f"Promote Area {unique}"
    created: list[UUID] = []
    try:
        pending = await _persist(
            city=city,
            area=area,
            price="150",
            outcome="insufficient_evidence",
            picker_id=f"promote-pending-{unique}",
        )
        created.append(pending.id)
        for index in range(5):
            evidence = await _persist(
                city=city,
                area=area,
                price=str(100 + index * 2),
                outcome="pass",
                picker_id=f"promote-evidence-{unique}-{index}",
            )
            created.append(evidence.id)

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

        async with SessionLocal() as session:
            stored = await session.get(Report, pending.id)
            assert stored is not None
            assert stored.status == "accepted"
            assert stored.is_anomalous is False
            assert stored.anomaly_outcome == "pass"
            assert stored.raw_text == "fixture raw picker message"
            count = await session.scalar(
                select(func.count(Report.id)).where(Report.id == pending.id)
            )
            assert count == 1
    finally:
        await _delete(created)


async def test_reevaluation_flags_pending_when_anomalous_evidence_arrives(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Flag City {unique}"
    area = f"Flag Area {unique}"
    created: list[UUID] = []
    try:
        pending = await _persist(
            city=city,
            area=area,
            price="9999",
            outcome="insufficient_evidence",
            picker_id=f"flag-pending-{unique}",
        )
        created.append(pending.id)
        for index in range(5):
            evidence = await _persist(
                city=city,
                area=area,
                price=str(100 + index),
                outcome="pass",
                picker_id=f"flag-evidence-{unique}-{index}",
            )
            created.append(evidence.id)

        async with SessionLocal() as session:
            result = await reevaluate_pending_report(
                session,
                report_id=pending.id,
                settings=Settings(),
            )

        assert result is not None
        assert result.transitioned is True
        assert result.status == "flagged"
        assert result.outcome == "suspicious"

        async with SessionLocal() as session:
            stored = await session.get(Report, pending.id)
            assert stored is not None
            assert stored.status == "flagged"
            assert stored.is_anomalous is True
            assert stored.anomaly_outcome == "suspicious"
            assert stored.anomaly_method == "mad"
    finally:
        await _delete(created)


async def test_reevaluation_infrastructure_failure_leaves_pending_unchanged(
    postgres_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unique = uuid4().hex
    city = f"Failure City {unique}"
    created: list[UUID] = []
    try:
        pending = await _persist(
            city=city,
            area=None,
            price="150",
            outcome="insufficient_evidence",
            picker_id=f"failure-pending-{unique}",
        )
        created.append(pending.id)

        async def explode(*_args: Any, **_kwargs: Any) -> AnomalyVerdict:
            raise RuntimeError("database connection reset")

        monkeypatch.setattr(
            reevaluation_module,
            "evaluate_report_statistical_with_session",
            explode,
        )

        async with SessionLocal() as session:
            result = await reevaluate_pending_report(
                session,
                report_id=pending.id,
                settings=Settings(),
            )

        assert result is not None
        assert result.transitioned is False
        assert result.status == "pending_evidence"

        async with SessionLocal() as session:
            stored = await session.get(Report, pending.id)
            assert stored is not None
            assert stored.status == "pending_evidence"
            assert stored.anomaly_outcome == "insufficient_evidence"
            assert stored.is_anomalous is False
    finally:
        await _delete(created)


async def test_concurrent_reevaluation_has_one_consistent_transition(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Concurrent City {unique}"
    area = f"Concurrent Area {unique}"
    created: list[UUID] = []
    try:
        pending = await _persist(
            city=city,
            area=area,
            price="150",
            outcome="insufficient_evidence",
            picker_id=f"concurrent-pending-{unique}",
        )
        created.append(pending.id)
        for index in range(5):
            evidence = await _persist(
                city=city,
                area=area,
                price=str(100 + index),
                outcome="pass",
                picker_id=f"concurrent-evidence-{unique}-{index}",
            )
            created.append(evidence.id)

        async def run_once():
            async with SessionLocal() as session:
                return await reevaluate_pending_report(
                    session,
                    report_id=pending.id,
                    settings=Settings(),
                )

        first, second = await asyncio.gather(run_once(), run_once())
        assert first is not None
        assert second is not None
        assert {first.status, second.status} <= {"pending_evidence", "accepted"}

        async with SessionLocal() as session:
            stored = await session.get(Report, pending.id)
            assert stored is not None
            assert stored.status == "accepted"
            count = await session.scalar(
                select(func.count(Report.id)).where(
                    Report.picker_id == f"concurrent-pending-{unique}"
                )
            )
            assert count == 1
    finally:
        await _delete(created)


async def test_batch_reevaluation_processes_only_pending_reports(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Batch City {unique}"
    area = f"Batch Area {unique}"
    created: list[UUID] = []
    try:
        pending = await _persist(
            city=city,
            area=area,
            price="150",
            outcome="insufficient_evidence",
            picker_id=f"batch-pending-{unique}",
        )
        created.append(pending.id)
        accepted = await _persist(
            city=city,
            area=area,
            price="100",
            outcome="pass",
            picker_id=f"batch-accepted-{unique}",
        )
        created.append(accepted.id)

        results = await reevaluate_pending_reports(
            settings=Settings(),
            limit=1000,
        )

        matching = [result for result in results if result.report_id == pending.id]
        assert len(matching) == 1
        assert matching[0].status == "pending_evidence"

        async with SessionLocal() as session:
            stored = await session.get(Report, accepted.id)
            assert stored is not None
            assert stored.status == "accepted"
            assert stored.anomaly_outcome == "pass"
    finally:
        await _delete(created)
