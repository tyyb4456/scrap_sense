"""Conservative, deterministic Tier 1 anomaly detection.

The detector compares a new report only with historical reports that share the
same normalized material, currency, unit, and city. It uses the median and the
median absolute deviation (MAD), which tolerate ordinary market spread much
better than a mean and standard deviation. A statistical outlier is labelled
``suspicious`` for review; it is never labelled fraud and never rejected
automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.config import Settings
from app.schemas.report import AnomalyVerdict, ReportDraft
from app.services.materials import material_aliases, normalize_material, normalize_text
from app.services.price_aggregation import (
    PriceObservation,
    as_utc,
    median_decimal,
    normalize_currency,
)
from app.services.reports import fetch_comparable_reports

logger = logging.getLogger(__name__)

MAD_SCALE = 0.6745
MAX_CONFIDENCE = 0.95


@dataclass(frozen=True)
class AnomalyPolicy:
    """Configurable Tier 1 thresholds. Defaults are intentionally cautious."""

    min_sample_size: int = 5
    max_observation_age_days: int = 90
    mad_z_threshold: float = 3.5
    min_relative_deviation: float = 0.5
    zero_mad_min_relative_deviation: float = 1.0


def policy_from_settings(settings: Settings) -> AnomalyPolicy:
    return AnomalyPolicy(
        min_sample_size=settings.anomaly_min_sample_size,
        max_observation_age_days=settings.anomaly_max_observation_age_days,
        mad_z_threshold=settings.anomaly_mad_z_threshold,
        min_relative_deviation=settings.anomaly_min_relative_deviation,
        zero_mad_min_relative_deviation=settings.anomaly_zero_mad_min_relative_deviation,
    )


def _insufficient(reason: str, *, method: str = "mad") -> AnomalyVerdict:
    return AnomalyVerdict(
        is_anomalous=False,
        reason=reason,
        method=method,
        confidence=0.0,
        outcome="insufficient_evidence",
    )


def _comparable_observations(
    *,
    observations: list[PriceObservation],
    material: str | None,
    currency: str | None,
    city: str | None,
    now: datetime,
    policy: AnomalyPolicy,
) -> list[PriceObservation]:
    aliases = set(material_aliases(material))
    normalized_currency = normalize_currency(currency)
    normalized_city = normalize_text(city)
    if not aliases or normalized_currency is None or normalized_city is None:
        return []

    cutoff = as_utc(now) - timedelta(days=policy.max_observation_age_days)
    comparable: list[PriceObservation] = []

    for observation in observations:
        if observation.status != "accepted" or observation.is_anomalous:
            continue
        if observation.unit != "kg":
            continue
        if observation.normalized_material not in aliases:
            continue
        if normalize_currency(observation.currency) != normalized_currency:
            continue
        if normalize_text(observation.city) != normalized_city:
            continue
        if observation.price_per_kg is None or not observation.price_per_kg.is_finite():
            continue
        if observation.price_per_kg <= 0:
            continue
        if observation.observed_at is None:
            continue
        observed_at = as_utc(observation.observed_at)
        if observed_at < cutoff or observed_at > as_utc(now) + timedelta(days=1):
            continue
        comparable.append(observation)

    return comparable


def evaluate_statistical_anomaly(
    *,
    material: str | None,
    price_per_kg: Decimal | None,
    currency: str | None,
    city: str | None,
    area: str | None,
    unit: str | None,
    observations: list[PriceObservation],
    now: datetime,
    policy: AnomalyPolicy,
) -> AnomalyVerdict:
    """Compare one candidate price with comparable historical observations."""
    if price_per_kg is None or not price_per_kg.is_finite() or price_per_kg <= 0:
        return _insufficient("Candidate price is not a finite positive value.")
    if (unit or "").strip().lower() != "kg":
        return _insufficient("Candidate unit is not kg; no cross-unit comparison is attempted.")
    if normalize_text(city) is None:
        return _insufficient(
            "A city is required before a report can be compared with historical prices."
        )
    if normalize_currency(currency) is None:
        return _insufficient("A currency is required before prices can be compared.")
    if normalize_material(material) is None:
        return _insufficient("A material is required before prices can be compared.")

    comparable = _comparable_observations(
        observations=observations,
        material=material,
        currency=currency,
        city=city,
        now=now,
        policy=policy,
    )

    area_name = normalize_text(area)
    local = (
        [
            observation
            for observation in comparable
            if normalize_text(observation.area) == area_name
        ]
        if area_name is not None
        else []
    )
    if area_name is not None and len(local) >= policy.min_sample_size:
        scope = "area"
        sample = local
    else:
        scope = "city"
        sample = comparable

    if len(sample) < policy.min_sample_size:
        return _insufficient(
            "Not enough comparable historical reports "
            f"({len(sample)} < {policy.min_sample_size}) to run a statistical check."
        )

    prices = [
        observation.price_per_kg
        for observation in sample
        if observation.price_per_kg is not None
    ]
    median = median_decimal(prices)
    if median is None or median <= 0:
        return _insufficient("Comparable prices could not be summarized.")

    deviations = [abs(price - median) for price in prices]
    mad = median_decimal(deviations)
    if mad is None:
        return _insufficient("Comparable prices could not be summarized.")

    relative_deviation = abs(price_per_kg - median) / median
    context = (
        f"{len(sample)} comparable {scope}-level reports; "
        f"median {median} {currency}/kg; MAD {mad}."
    )

    if mad == 0:
        if price_per_kg == median:
            return AnomalyVerdict(
                is_anomalous=False,
                reason=f"Price matches the comparable median. {context}",
                method="mad",
                confidence=0.6,
                outcome="pass",
                sample_size=len(sample),
                median_price_per_kg=median,
                mad_price_per_kg=mad,
            )
        if relative_deviation < Decimal(str(policy.zero_mad_min_relative_deviation)):
            return _insufficient(
                "Comparable prices show no dispersion; a small deviation cannot be "
                f"assessed statistically. {context}"
            )
        return AnomalyVerdict(
            is_anomalous=True,
            reason=(
                "Price is far from an otherwise identical comparable set with zero "
                f"MAD ({relative_deviation:.0%} relative deviation). {context}"
            ),
            method="mad",
            confidence=0.75,
            outcome="suspicious",
            sample_size=len(sample),
            median_price_per_kg=median,
            mad_price_per_kg=mad,
        )

    modified_z = MAD_SCALE * float(abs(price_per_kg - median) / mad)
    if (
        modified_z > policy.mad_z_threshold
        and relative_deviation >= Decimal(str(policy.min_relative_deviation))
    ):
        confidence = min(
            MAX_CONFIDENCE,
            0.6 + 0.05 * min(len(sample), 8) + 0.02 * (modified_z - policy.mad_z_threshold),
        )
        return AnomalyVerdict(
            is_anomalous=True,
            reason=(
                "Price is a statistical outlier: "
                f"modified z-score {modified_z:.2f} > {policy.mad_z_threshold}, "
                f"relative deviation {relative_deviation:.0%}. {context}"
            ),
            method="mad",
            confidence=round(confidence, 3),
            outcome="suspicious",
            sample_size=len(sample),
            median_price_per_kg=median,
            mad_price_per_kg=mad,
        )

    return AnomalyVerdict(
        is_anomalous=False,
        reason=(
            f"Price is within the comparable range (modified z-score {modified_z:.2f}). "
            f"{context}"
        ),
        method="mad",
        confidence=0.6,
        outcome="pass",
        sample_size=len(sample),
        median_price_per_kg=median,
        mad_price_per_kg=mad,
    )


async def evaluate_report_statistical(
    draft: ReportDraft,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> AnomalyVerdict:
    """Load comparable reports from PostgreSQL and run the Tier 1 check.

    Database failures are returned as an explicit ``unavailable`` outcome so the
    graph can continue safely instead of crashing or pretending a check passed.
    """
    from app.db.session import SessionLocal  # local import keeps pure tests DB-free

    evaluated_at = as_utc(now or datetime.now(UTC))
    policy = policy_from_settings(settings)

    if normalize_text(draft.city) is None:
        return _insufficient(
            "A city is required before a report can be compared with historical prices."
        )

    try:
        async with SessionLocal() as session:
            reports = await fetch_comparable_reports(
                session,
                material_aliases=set(material_aliases(draft.material)),
                city=normalize_text(draft.city) or "",
                currency=normalize_currency(draft.currency) or "",
                since=evaluated_at
                - timedelta(days=policy.max_observation_age_days),
                limit=settings.anomaly_max_comparisons,
            )
    except Exception:
        logger.exception("Deterministic anomaly comparison failed")
        return AnomalyVerdict(
            is_anomalous=False,
            reason="Historical comparison was unavailable; no anomaly conclusion was drawn.",
            method="mad",
            confidence=0.0,
            outcome="unavailable",
        )

    observations = [
        PriceObservation(
            report_id=report.id,
            picker_id=report.picker_id,
            material=report.material,
            price_per_kg=report.price_per_kg,
            quantity_kg=report.quantity_kg,
            currency=report.currency,
            city=report.city,
            area=report.area,
            observed_at=as_utc(report.effective_observed_at),
            status=report.status,
            is_anomalous=report.is_anomalous,
            unit="kg",
        )
        for report in reports
    ]

    return evaluate_statistical_anomaly(
        material=draft.material,
        price_per_kg=draft.price_per_kg,
        currency=draft.currency,
        city=draft.city,
        area=draft.area,
        unit=draft.unit,
        observations=observations,
        now=evaluated_at,
        policy=policy,
    )
