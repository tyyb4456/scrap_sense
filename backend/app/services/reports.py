"""Persist finalized scrap reports produced by the intake pipeline."""

from __future__ import annotations

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
