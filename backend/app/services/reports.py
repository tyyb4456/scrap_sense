"""Persist and read finalized scrap reports."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.report import Report
from app.schemas.report import AnomalyVerdict, FinalReport, ReportDraft


async def save_report(
    *,
    picker_id: str,
    raw_text: str,
    draft: ReportDraft,
    verdict: AnomalyVerdict,
) -> FinalReport:
    """Store a validated report and return its persisted representation."""
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
        confidence=draft.confidence,
        is_anomalous=verdict.is_anomalous,
        anomaly_reason=verdict.reason,
        anomaly_method=verdict.method,
        status="flagged" if verdict.is_anomalous else "accepted",
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
            Report.status == "accepted",
            Report.is_anomalous.is_(False),
            Report.price_per_kg > 0,
            Report.created_at >= since,
            func.lower(func.trim(Report.currency)) == currency.lower(),
            func.lower(func.trim(Report.city)) == city,
            func.lower(func.trim(Report.material)).in_(sorted(material_aliases)),
        )
        .order_by(Report.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars())
