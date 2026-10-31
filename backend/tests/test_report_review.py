from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes import reports as reports_route
from app.auth import ClerkUser, require_admin, require_auth
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import app
from app.models.report import Report
from app.services.reports import (
    ReportApprovalNotEligible,
    ReportReviewConflict,
    review_report,
)

USER = ClerkUser(user_id="reviewer_1", session_id="sess_1", claims={})
REPORT_ID = uuid4()
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


class FakeSession:
    def __init__(self, report: Report | None) -> None:
        self.report = report
        self.committed = False
        self.rolled_back = False

    async def get(self, _model: Any, _id: Any, **_kwargs: Any) -> Report | None:
        return self.report

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, _report: Any) -> None:
        return None


def report_model(
    *,
    status: str = "flagged",
    is_anomalous: bool = True,
    city: str | None = "Multan",
    anomaly_outcome: str | None = None,
) -> Report:
    if anomaly_outcome is None:
        anomaly_outcome = "suspicious" if is_anomalous else "pass"
    return Report(
        id=REPORT_ID,
        picker_id="picker_1",
        raw_text="fixture",
        material="plastic",
        price_per_kg=Decimal("150"),
        quantity_kg=Decimal("2"),
        currency="PKR",
        city=city,
        area=None,
        confidence=0.8,
        is_anomalous=is_anomalous,
        anomaly_reason="Price is a statistical outlier.",
        anomaly_method="mad",
        anomaly_outcome=anomaly_outcome,
        status=status,
    )


async def test_approval_clears_the_active_flag() -> None:
    session = FakeSession(report_model())

    result = await review_report(
        session,  # type: ignore[arg-type]
        report_id=REPORT_ID,
        reviewer_id="reviewer_1",
        status="accepted",
    )

    assert result is not None
    assert result.status == "accepted"
    assert result.is_anomalous is False
    assert result.reviewed_at is not None
    assert result.reviewed_by == "reviewer_1"
    assert session.committed is True


async def test_approval_cannot_bypass_the_city_requirement() -> None:
    session = FakeSession(report_model(city=None))

    with pytest.raises(ReportApprovalNotEligible) as raised:
        await review_report(
            session,  # type: ignore[arg-type]
            report_id=REPORT_ID,
            reviewer_id="reviewer_1",
            status="accepted",
        )

    assert "city" in raised.value.reason
    assert session.committed is False
    assert session.rolled_back is True
    assert session.report is not None
    assert session.report.status == "flagged"
    assert session.report.is_anomalous is True
    assert session.report.reviewed_at is None


async def test_approval_cannot_bypass_an_incomplete_tier1_check() -> None:
    session = FakeSession(
        report_model(
            status="flagged",
            is_anomalous=False,
            anomaly_outcome="unknown",
        )
    )

    with pytest.raises(ReportApprovalNotEligible) as raised:
        await review_report(
            session,  # type: ignore[arg-type]
            report_id=REPORT_ID,
            reviewer_id="reviewer_1",
            status="accepted",
        )

    assert "anomaly check" in raised.value.reason
    assert session.committed is False
    assert session.rolled_back is True
    assert session.report is not None
    assert session.report.status == "flagged"
    assert session.report.is_anomalous is False
    assert session.report.reviewed_at is None


async def test_rejection_is_still_allowed_for_a_cityless_report() -> None:
    session = FakeSession(report_model(city=None))

    result = await review_report(
        session,  # type: ignore[arg-type]
        report_id=REPORT_ID,
        reviewer_id="reviewer_1",
        status="rejected",
    )

    assert result is not None
    assert result.status == "rejected"
    assert result.is_anomalous is True
    assert session.committed is True


async def test_rejection_keeps_the_row_but_excludes_it_by_status() -> None:
    session = FakeSession(report_model())

    result = await review_report(
        session,  # type: ignore[arg-type]
        report_id=REPORT_ID,
        reviewer_id="reviewer_1",
        status="rejected",
    )

    assert result is not None
    assert result.status == "rejected"
    assert result.is_anomalous is True
    assert result.reviewed_at is not None


async def test_pending_evidence_cannot_be_approved() -> None:
    session = FakeSession(
        report_model(
            status="pending_evidence",
            is_anomalous=False,
            anomaly_outcome="insufficient_evidence",
        )
    )

    with pytest.raises(ReportApprovalNotEligible) as raised:
        await review_report(
            session,  # type: ignore[arg-type]
            report_id=REPORT_ID,
            reviewer_id="reviewer_1",
            status="accepted",
        )

    assert "pending-evidence" in raised.value.reason
    assert session.committed is False
    assert session.rolled_back is True
    assert session.report is not None
    assert session.report.status == "pending_evidence"
    assert session.report.reviewed_at is None


async def test_pending_evidence_can_be_rejected_for_disposal() -> None:
    session = FakeSession(
        report_model(
            status="pending_evidence",
            is_anomalous=False,
            anomaly_outcome="insufficient_evidence",
        )
    )

    result = await review_report(
        session,  # type: ignore[arg-type]
        report_id=REPORT_ID,
        reviewer_id="reviewer_1",
        status="rejected",
    )

    assert result is not None
    assert result.status == "rejected"
    assert result.anomaly_outcome == "insufficient_evidence"
    assert result.reviewed_by == "reviewer_1"
    assert session.committed is True


async def test_already_decided_reports_cannot_be_reviewed_again() -> None:
    session = FakeSession(report_model(status="accepted", is_anomalous=False))

    with pytest.raises(ReportReviewConflict) as raised:
        await review_report(
            session,  # type: ignore[arg-type]
            report_id=REPORT_ID,
            reviewer_id="reviewer_1",
            status="rejected",
        )

    assert raised.value.current_status == "accepted"
    assert session.rolled_back is True
    assert session.committed is False
    assert session.report is not None
    assert session.report.status == "accepted"
    assert session.report.is_anomalous is False


def clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_review_endpoint_returns_the_updated_status(
    monkeypatch: Any,
) -> None:
    reviewed = SimpleNamespace(
        id=REPORT_ID,
        status="accepted",
        is_anomalous=False,
        reviewed_at=NOW,
    )

    async def fake_review(*_args: Any, **_kwargs: Any) -> Any:
        return reviewed

    monkeypatch.setattr(reports_route, "review_report", fake_review)
    app.dependency_overrides[require_admin] = lambda: USER
    app.dependency_overrides[get_session] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/reports/{REPORT_ID}/review",
                json={"status": "accepted"},
            )
    finally:
        clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["is_anomalous"] is False
    assert body["reviewed_by"] == "reviewer_1"


def test_review_endpoint_returns_404_for_an_unknown_report(monkeypatch: Any) -> None:
    async def fake_review(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(reports_route, "review_report", fake_review)
    app.dependency_overrides[require_admin] = lambda: USER
    app.dependency_overrides[get_session] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/reports/{REPORT_ID}/review",
                json={"status": "rejected"},
            )
    finally:
        clear_overrides()

    assert response.status_code == 404


def test_review_endpoint_rejects_an_ineligible_approval(monkeypatch: Any) -> None:
    async def fake_review(*_args: Any, **_kwargs: Any) -> Any:
        raise ReportApprovalNotEligible("a valid city is required for price estimation")

    monkeypatch.setattr(reports_route, "review_report", fake_review)
    app.dependency_overrides[require_admin] = lambda: USER
    app.dependency_overrides[get_session] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/reports/{REPORT_ID}/review",
                json={"status": "accepted"},
            )
    finally:
        clear_overrides()

    assert response.status_code == 409
    assert "city" in response.json()["detail"]


def test_review_endpoint_requires_an_configured_reviewer() -> None:
    app.dependency_overrides[require_auth] = lambda: USER
    app.dependency_overrides[get_settings] = lambda: Settings(admin_user_ids=[])
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/reports/{REPORT_ID}/review",
                json={"status": "accepted"},
            )
    finally:
        clear_overrides()

    assert response.status_code == 403
