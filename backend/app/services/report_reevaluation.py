"""Controlled re-evaluation of reports saved as ``pending_evidence``.

A pending report is never promoted automatically because time passed or because
other reports arrived. It must be explicitly re-evaluated with the same
deterministic Tier 1 algorithm and thresholds used at intake. The operation locks
the report row so concurrent workers cannot apply conflicting transitions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models.report import Report
from app.schemas.report import (
    AnomalyVerdict,
    ReportDraft,
    tier1_check_completed,
    tier1_check_insufficient,
)
from app.services.anomaly_detection import evaluate_report_statistical_with_session
from app.services.price_aggregation import as_utc
from app.services.reports import (
    REPORT_STATUS_ACCEPTED,
    REPORT_STATUS_FLAGGED,
    REPORT_STATUS_PENDING_EVIDENCE,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReevaluationResult:
    """Outcome of one re-evaluation attempt."""

    report_id: UUID
    status: str
    outcome: str
    transitioned: bool


def _draft_from_report(report: Report) -> ReportDraft:
    return ReportDraft(
        material=report.material,
        price_per_kg=report.price_per_kg,
        quantity_kg=report.quantity_kg,
        currency=report.currency,
        unit="kg",
        city=report.city,
        area=report.area,
        observed_at=report.observed_at,
        confidence=report.confidence,
    )


def _apply_verdict(report: Report, verdict: AnomalyVerdict) -> str:
    report.anomaly_outcome = verdict.outcome
    report.anomaly_reason = verdict.reason
    report.anomaly_method = verdict.method

    if verdict.outcome == "pass" and not verdict.is_anomalous:
        report.status = REPORT_STATUS_ACCEPTED
        report.is_anomalous = False
        return REPORT_STATUS_ACCEPTED

    if verdict.outcome == "suspicious" or verdict.is_anomalous:
        report.status = REPORT_STATUS_FLAGGED
        report.is_anomalous = True
        return REPORT_STATUS_FLAGGED

    report.status = REPORT_STATUS_PENDING_EVIDENCE
    report.is_anomalous = False
    return REPORT_STATUS_PENDING_EVIDENCE


async def reevaluate_pending_report(
    session: AsyncSession,
    *,
    report_id: UUID,
    settings: Settings,
    now: datetime | None = None,
) -> ReevaluationResult | None:
    """Re-evaluate one pending report under a row lock.

    Returns ``None`` when the report does not exist. A report that is no longer
    pending is returned unchanged with ``transitioned=False``. If Tier 1 cannot
    run, the transaction is rolled back and the pending row is left untouched.
    """
    report = await session.get(Report, report_id, with_for_update=True)
    if report is None:
        return None

    report_id_value = report.id
    original_status = report.status
    original_outcome = report.anomaly_outcome
    if original_status != REPORT_STATUS_PENDING_EVIDENCE:
        return ReevaluationResult(
            report_id=report_id_value,
            status=original_status,
            outcome=original_outcome,
            transitioned=False,
        )

    try:
        verdict = await evaluate_report_statistical_with_session(
            _draft_from_report(report),
            session=session,
            settings=settings,
            now=as_utc(now or datetime.now(UTC)),
        )
    except Exception:
        logger.exception(
            "Re-evaluation infrastructure failure for report %s",
            report_id_value,
        )
        try:
            await session.rollback()
        except Exception:  # pragma: no cover - defensive rollback
            logger.exception("Could not roll back failed re-evaluation")
        return ReevaluationResult(
            report_id=report_id_value,
            status=original_status,
            outcome=original_outcome,
            transitioned=False,
        )

    if not (tier1_check_completed(verdict) or tier1_check_insufficient(verdict)):
        logger.warning(
            "Leaving report %s pending because Tier 1 was unavailable (outcome=%s)",
            report_id_value,
            verdict.outcome,
        )
        await session.rollback()
        return ReevaluationResult(
            report_id=report_id_value,
            status=original_status,
            outcome=verdict.outcome,
            transitioned=False,
        )

    new_status = _apply_verdict(report, verdict)
    await session.commit()
    await session.refresh(report)
    logger.info(
        "Re-evaluated report %s: outcome=%s status=%s",
        report.id,
        verdict.outcome,
        new_status,
    )
    return ReevaluationResult(
        report_id=report.id,
        status=new_status,
        outcome=verdict.outcome,
        transitioned=True,
    )


async def reevaluate_pending_reports(
    *,
    settings: Settings | None = None,
    limit: int = 100,
    now: datetime | None = None,
) -> list[ReevaluationResult]:
    """Re-evaluate a bounded batch of pending reports.

    Each report gets its own session and transaction so one infrastructure
    failure cannot corrupt or roll back another report's state.
    """
    resolved_settings = settings or get_settings()
    evaluated_at = as_utc(now or datetime.now(UTC))

    try:
        async with SessionLocal() as session:
            report_ids = list(
                (
                    await session.scalars(
                        select(Report.id)
                        .where(Report.status == REPORT_STATUS_PENDING_EVIDENCE)
                        .order_by(Report.created_at.asc(), Report.id.asc())
                        .limit(limit)
                    )
                ).all()
            )
    except Exception:
        logger.exception("Could not load pending reports for re-evaluation")
        return []

    results: list[ReevaluationResult] = []
    for report_id in report_ids:
        try:
            async with SessionLocal() as session:
                result = await reevaluate_pending_report(
                    session,
                    report_id=report_id,
                    settings=resolved_settings,
                    now=evaluated_at,
                )
        except Exception:
            logger.exception("Re-evaluation failed for report %s", report_id)
            continue
        if result is not None:
            results.append(result)
    return results


async def _main() -> None:
    results = await reevaluate_pending_reports()
    transitions = sum(1 for result in results if result.transitioned)
    logger.info(
        "Re-evaluated %d pending reports; %d transitioned",
        len(results),
        transitions,
    )


if __name__ == "__main__":  # pragma: no cover - operational entry point
    asyncio.run(_main())
