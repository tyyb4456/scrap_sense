"""Persist and read finalized scrap reports."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.session import SessionLocal
from app.models.report import Report
from app.schemas.report import (
    AnomalyVerdict,
    FinalReport,
    ReportDraft,
    tier1_check_completed,
    tier1_check_insufficient,
)
from app.services.price_aggregation import as_utc
from app.services.report_validation import normalize_city, validate_report_draft

REPORT_STATUS_ACCEPTED = "accepted"
REPORT_STATUS_FLAGGED = "flagged"
REPORT_STATUS_REJECTED = "rejected"
REPORT_STATUS_PENDING_EVIDENCE = "pending_evidence"
REPORT_STATUSES = frozenset(
    {
        REPORT_STATUS_ACCEPTED,
        REPORT_STATUS_FLAGGED,
        REPORT_STATUS_REJECTED,
        REPORT_STATUS_PENDING_EVIDENCE,
    }
)


class ReportReviewConflict(Exception):
    """The report is not in a state that permits a human review decision."""

    def __init__(self, current_status: str) -> None:
        self.current_status = current_status
        super().__init__(f"report status {current_status!r} cannot be reviewed")


class ReportApprovalNotEligible(Exception):
    """The report cannot enter the pricing dataset even with human approval."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ReportProcessingUnavailable(Exception):
    """The mandatory Tier 1 anomaly check did not produce a conclusion."""

    def __init__(self, outcome: str) -> None:
        self.outcome = outcome
        super().__init__(f"Tier 1 anomaly check did not complete (outcome={outcome!r})")


def pricing_ineligibility_reason(report: Report) -> str | None:
    """Return a mandatory pricing-eligibility problem, or ``None``.

    A city is the minimum geography required by both anomaly comparison and price
    aggregation. Historical rows are never rewritten; they simply remain
    ineligible until a valid city exists in the stored data.
    """
    if normalize_city(report.city) is None:
        return "a valid city is required for price estimation"
    return None


def trusted_report_condition() -> ColumnElement[bool]:
    """SQL condition for reports that may contribute trusted evidence.

    Accepted reports with a verified ``pass`` outcome qualify. A statistically
    suspicious report may qualify only after a reviewer approved it, which is
    represented by an accepted, non-anomalous row with ``reviewed_at`` set.
    Pending, flagged, rejected, unknown, and unavailable outcomes never qualify.
    """
    return and_(
        Report.status == REPORT_STATUS_ACCEPTED,
        Report.is_anomalous.is_(False),
        or_(
            Report.anomaly_outcome == "pass",
            and_(
                Report.anomaly_outcome == "suspicious",
                Report.reviewed_at.is_not(None),
            ),
        ),
    )


async def save_report(
    *,
    picker_id: str,
    raw_text: str,
    draft: ReportDraft,
    verdict: AnomalyVerdict,
) -> FinalReport:
    """Store a validated report and return its persisted representation.

    ``accepted`` means the report passed Tier 1 and may influence price
    aggregation. ``flagged`` means it is suspicious and must stay out of
    aggregation until an authorized reviewer approves it. ``pending_evidence``
    means Tier 1 ran successfully but lacked enough history; the row is stored
    for controlled evidence accumulation and is never treated as verified.

    A report whose mandatory Tier 1 check could not run (``unavailable``,
    ``error``, ``disabled``, or a missing verdict) is never persisted. The caller
    must fail the processing attempt safely instead of storing a normal-looking
    or suspicious-looking row.
    """
    validation = validate_report_draft(draft)
    if not validation.is_valid:
        raise ValueError(
            "Cannot persist an invalid report: "
            + ", ".join(issue.code for issue in validation.issues)
        )
    if draft.material is None or draft.price_per_kg is None or draft.quantity_kg is None:
        raise ValueError("Cannot persist a report missing material, price, or quantity")
    if not (tier1_check_completed(verdict) or tier1_check_insufficient(verdict)):
        raise ReportProcessingUnavailable(verdict.outcome)

    if tier1_check_insufficient(verdict):
        status = REPORT_STATUS_PENDING_EVIDENCE
        flagged = False
    else:
        flagged = verdict.is_anomalous or verdict.outcome == "suspicious"
        status = REPORT_STATUS_FLAGGED if flagged else REPORT_STATUS_ACCEPTED

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
        is_anomalous=flagged,
        anomaly_reason=verdict.reason,
        anomaly_method=verdict.method,
        anomaly_outcome=verdict.outcome,
        status=status,
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
            trusted_report_condition(),
            Report.price_per_kg > 0,
            func.coalesce(Report.observed_at, Report.created_at) >= since,
            func.lower(func.trim(Report.currency)) == currency.lower(),
            Report.city.is_not(None),
            func.trim(Report.city) != "",
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
            trusted_report_condition(),
            Report.price_per_kg > 0,
            func.coalesce(Report.observed_at, Report.created_at) >= since,
            func.lower(func.trim(Report.currency)) == currency.lower(),
            Report.city.is_not(None),
            func.trim(Report.city) != "",
            func.lower(func.trim(Report.city)) == city,
            func.lower(func.trim(Report.material)).in_(sorted(material_aliases)),
        )
        .order_by(Report.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars())


async def list_reports_for_review(
    session: AsyncSession,
    *,
    status: str,
    offset: int,
    limit: int,
) -> tuple[list[Report], int]:
    """Return one page of reports and the matching total for reviewer use.

    Ordering is oldest first, with the report id as a stable tie-breaker so
    pagination cannot skip or repeat a row. No relationships are loaded, so a
    page costs two queries regardless of its size.
    """
    if status not in REPORT_STATUSES:
        raise ValueError("unsupported report status")

    condition = Report.status == status
    total = await session.scalar(select(func.count(Report.id)).where(condition))
    statement = (
        select(Report)
        .where(condition)
        .order_by(Report.created_at.asc(), Report.id.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars()), int(total or 0)


async def get_report_for_review(
    session: AsyncSession,
    *,
    report_id: UUID,
) -> Report | None:
    """Load one report for the reviewer detail view."""
    return await session.get(Report, report_id)


async def review_report(
    session: AsyncSession,
    *,
    report_id: UUID,
    reviewer_id: str,
    status: str,
) -> Report | None:
    """Approve or reject a report after human review.

    Only a ``flagged`` report can be approved. A ``pending_evidence`` report
    cannot be approved because Tier 1 never produced a sufficient statistical
    conclusion; it must first be re-evaluated. Rejection remains available for
    both flagged and pending rows as a disposal path.

    Approval requires a completed suspicious statistical outcome, clears the
    active anomaly flag, and preserves the original statistical outcome for
    audit. It is refused when the stored report lacks a valid city because such a
    report can never enter the pricing dataset. Rejection keeps the row for audit
    but excludes it by status. Original anomaly evidence is not erased.

    The row is locked for the duration of the decision so two reviewers cannot
    apply conflicting transitions to the same report.
    """
    if status not in {REPORT_STATUS_ACCEPTED, REPORT_STATUS_REJECTED}:
        raise ValueError("review status must be accepted or rejected")

    report = await session.get(Report, report_id, with_for_update=True)
    if report is None:
        return None

    current_status = report.status
    if current_status not in {REPORT_STATUS_FLAGGED, REPORT_STATUS_PENDING_EVIDENCE}:
        await session.rollback()
        raise ReportReviewConflict(current_status)

    if status == REPORT_STATUS_ACCEPTED:
        if current_status == REPORT_STATUS_PENDING_EVIDENCE:
            await session.rollback()
            raise ReportApprovalNotEligible(
                "a pending-evidence report cannot be approved before a successful "
                "Tier 1 re-evaluation"
            )
        if not report.is_anomalous or report.anomaly_outcome != "suspicious":
            await session.rollback()
            raise ReportApprovalNotEligible(
                "the statistical anomaly check did not complete for this report"
            )
        reason = pricing_ineligibility_reason(report)
        if reason is not None:
            await session.rollback()
            raise ReportApprovalNotEligible(reason)

    report.status = status
    report.reviewed_at = datetime.now(UTC)
    report.reviewed_by = reviewer_id
    if status == REPORT_STATUS_ACCEPTED:
        report.is_anomalous = False

    await session.commit()
    await session.refresh(report)
    return report
