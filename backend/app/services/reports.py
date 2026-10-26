"""Persist and read finalized scrap reports."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.report import Report
from app.schemas.report import AnomalyVerdict, FinalReport, ReportDraft
from app.services.price_aggregation import as_utc
from app.services.report_validation import validate_report_draft

REPORT_STATUS_ACCEPTED = "accepted"
REPORT_STATUS_FLAGGED = "flagged"
REPORT_STATUS_REJECTED = "rejected"


async def save_report(
    *,
    picker_id: str,
    raw_text: str,
    draft: ReportDraft,
    verdict: AnomalyVerdict,
) -> FinalReport:
    """Store a validated report and return its persisted representation.

    ``accepted`` means the report passed the available automatic checks and may
    influence price aggregation. ``flagged`` means it is suspicious and must
    stay out of aggregation until an authorized reviewer approves it.
    """
    validation = validate_report_draft(draft)
    if not validation.is_valid:
        raise ValueError(
            "Cannot persist an invalid report: "
            + ", ".join(issue.code for issue in validation.issues)
        )
    if draft.material is None or draft.price_per_kg is None or draft.quantity_kg is None:
        raise ValueError("Cannot persist a report missing material, price, or quantity")

    report = Report(
        picker_id=picker_id,
        raw_text=raw_text,
        material=draft.material,
        price_per_kg=draft.price_per_kg,
        quantity_kg=draft.quantity_kg,
        currency=draft.currency,
        city=draft.city,
        area=draft.area,
        observed_at=as_utc(draft.observed_at) if draft.observed_at is not None else None,
        confidence=draft.confidence,
        is_anomalous=verdict.is_anomalous,
        anomaly_reason=verdict.reason,
        anomaly_method=verdict.method,
        status=REPORT_STATUS_FLAGGED if verdict.is_anomalous else REPORT_STATUS_ACCEPTED,
    )

    async with SessionLocal() as session:
        session.add(report)
        await session.commit()
        await session.refresh(report)
        return FinalReport.model_validate(report)


async def fetch_reports_for_pricing(
    session: AsyncSession,
    *,
    material_aliases: set[str],
    city: str,
    currency: str,
    since: datetime,
    limit: int,
) -> list[Report]:
    """Return a bounded, filtered set of candidate reports for aggregation.

    Only accepted, non-anomalous reports in the requested city and currency are
    read. The service re-validates every row, so this query is an efficiency
    filter rather than the sole eligibility boundary.
    """
    if not material_aliases:
        return []

    statement = (
        select(Report)
        .where(
            Report.status == REPORT_STATUS_ACCEPTED,
            Report.is_anomalous.is_(False),
            Report.price_per_kg > 0,
            func.coalesce(Report.observed_at, Report.created_at) >= since,
            func.lower(func.trim(Report.currency)) == currency.lower(),
            func.lower(func.trim(Report.city)) == city,
            func.lower(func.trim(Report.material)).in_(sorted(material_aliases)),
        )
        .order_by(Report.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars())


async def fetch_comparable_reports(
    session: AsyncSession,
    *,
    material_aliases: set[str],
    city: str,
    currency: str,
    since: datetime,
    limit: int,
) -> list[Report]:
    """Return accepted, non-anomalous rows used by the Tier 1 comparison.

    The same material/currency/city/age dimensions are applied again by the pure
    detector, so this query is an efficiency prefilter rather than the only
    correctness boundary.
    """
    if not material_aliases or not city or not currency:
        return []

    statement = (
        select(Report)
        .where(
            Report.status == REPORT_STATUS_ACCEPTED,
            Report.is_anomalous.is_(False),
            Report.price_per_kg > 0,
            func.coalesce(Report.observed_at, Report.created_at) >= since,
            func.lower(func.trim(Report.currency)) == currency.lower(),
            func.lower(func.trim(Report.city)) == city,
            func.lower(func.trim(Report.material)).in_(sorted(material_aliases)),
        )
        .order_by(Report.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars())


async def review_report(
    session: AsyncSession,
    *,
    report_id: UUID,
    reviewer_id: str,
    status: str,
) -> Report | None:
    """Approve or reject a report after human review.

    Approval clears the active anomaly flag so the report can influence price
    aggregation again. Rejection keeps the row for audit but excludes it by
    status. Original anomaly evidence is not erased.
    """
    if status not in {REPORT_STATUS_ACCEPTED, REPORT_STATUS_REJECTED}:
        raise ValueError("review status must be accepted or rejected")

    report = await session.get(Report, report_id)
    if report is None:
        return None

    report.status = status
    report.reviewed_at = datetime.now(UTC)
    report.reviewed_by = reviewer_id
    if status == REPORT_STATUS_ACCEPTED:
        report.is_anomalous = False

    await session.commit()
    await session.refresh(report)
    return report
