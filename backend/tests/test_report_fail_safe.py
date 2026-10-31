"""Fail-safe behavior for incomplete Tier 1 anomaly checks.

These tests exercise the persistence and pure pricing boundaries directly. They
do not require a live database or LLM provider.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.schemas.report import AnomalyVerdict, ReportDraft
from app.services import reports as reports_module
from app.services.price_aggregation import (
    PriceObservation,
    eligibility_reason,
    evaluate_price,
)
from app.services.reports import ReportProcessingUnavailable, save_report

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


class _ExplodingSessionFactory:
    def __call__(self) -> Any:
        raise AssertionError("SessionLocal must not be opened for an incomplete check")


class _CapturingSession:
    def __init__(self, captured: list[Any]) -> None:
        self.captured = captured

    async def __aenter__(self) -> _CapturingSession:
        return self

    async def __aexit__(self, *_args: Any) -> bool:
        return False

    def add(self, report: Any) -> None:
        self.captured.append(report)

    async def commit(self) -> None:
        return None

    async def refresh(self, report: Any) -> None:
        if report.id is None:
            report.id = uuid.uuid4()
        if report.created_at is None:
            report.created_at = NOW
        if report.updated_at is None:
            report.updated_at = NOW


class _CapturingSessionFactory:
    def __init__(self, captured: list[Any]) -> None:
        self.captured = captured

    def __call__(self) -> _CapturingSession:
        return _CapturingSession(self.captured)


def _draft() -> ReportDraft:
    return ReportDraft(
        material="plastic",
        price_per_kg=Decimal("150"),
        quantity_kg=Decimal("2"),
        currency="PKR",
        unit="kg",
        city="Multan",
        area="Shah Rizwan",
        observed_at=NOW - timedelta(days=1),
    )


def _verdict(
    *,
    outcome: str,
    is_anomalous: bool = False,
    reason: str = "Historical comparison was unavailable.",
) -> AnomalyVerdict:
    return AnomalyVerdict(
        is_anomalous=is_anomalous,
        reason=reason,
        method="mad",
        confidence=0.0,
        outcome=outcome,  # type: ignore[arg-type]
    )


async def test_save_report_refuses_unavailable_before_opening_a_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reports_module, "SessionLocal", _ExplodingSessionFactory())

    with pytest.raises(ReportProcessingUnavailable) as raised:
        await save_report(
            picker_id="picker_1",
            raw_text="sold 2kg plastic at 150 per kg in Multan",
            draft=_draft(),
            verdict=_verdict(outcome="unavailable"),
        )

    assert raised.value.outcome == "unavailable"


async def test_save_report_persists_insufficient_evidence_as_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Any] = []
    monkeypatch.setattr(
        reports_module,
        "SessionLocal",
        _CapturingSessionFactory(captured),
    )

    saved = await save_report(
        picker_id="picker_1",
        raw_text="sold 2kg plastic at 150 per kg in Multan",
        draft=_draft(),
        verdict=_verdict(
            outcome="insufficient_evidence",
            reason="Not enough comparable historical reports.",
        ),
    )

    assert saved.status == "pending_evidence"
    assert saved.is_anomalous is False
    assert saved.anomaly_outcome == "insufficient_evidence"
    assert len(captured) == 1
    assert captured[0].status == "pending_evidence"
    assert captured[0].raw_text == "sold 2kg plastic at 150 per kg in Multan"


def _observation(
    *,
    price: str = "150",
    outcome: str = "pass",
    status: str = "accepted",
    is_anomalous: bool = False,
    area: str = "Shah Rizwan",
    picker_id: str | None = None,
) -> PriceObservation:
    return PriceObservation(
        report_id=uuid.uuid4(),
        picker_id=picker_id or f"picker-{uuid.uuid4()}",
        material="plastic",
        price_per_kg=Decimal(price),
        quantity_kg=Decimal("2"),
        currency="PKR",
        city="Multan",
        area=area,
        observed_at=NOW - timedelta(days=1),
        status=status,
        is_anomalous=is_anomalous,
        anomaly_outcome=outcome,
    )


def _evaluate(observations: list[PriceObservation]) -> Any:
    return evaluate_price(
        material="plastic",
        location="Multan",
        area="Shah Rizwan",
        observations=observations,
        seed_prices=[],
        now=NOW,
        min_observations=3,
    )


def test_unavailable_observations_are_ineligible_for_pricing() -> None:
    unavailable = _observation(price="9999", outcome="unavailable")
    assert eligibility_reason(unavailable) == "anomaly_outcome:unavailable"

    result = _evaluate(
        [
            unavailable,
            _observation(price="100"),
            _observation(price="200"),
            _observation(price="300"),
        ]
    ).estimate

    assert result.source == "local_reports"
    assert result.observation_count == 3
    assert result.estimated_price_per_kg == 200.0
    assert result.observed_max_price_per_kg == 300.0


def test_only_unavailable_observations_return_unavailable() -> None:
    result = _evaluate(
        [
            _observation(price="100", outcome="unavailable"),
            _observation(price="200", outcome="insufficient_evidence"),
            _observation(price="300", outcome="error"),
        ]
    ).estimate

    assert result.source == "unavailable"
    assert result.estimated_price_per_kg is None
    assert result.observation_count == 0


def test_accepted_non_anomalous_observations_still_contribute() -> None:
    result = _evaluate(
        [
            _observation(price="100"),
            _observation(price="200"),
            _observation(price="300"),
        ]
    ).estimate

    assert result.source == "local_reports"
    assert result.observation_count == 3
    assert result.estimated_price_per_kg == 200.0
