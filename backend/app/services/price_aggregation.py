"""Deterministic price aggregation and fallback selection.

This module contains no database or network access. The caller supplies
candidate observations and seed entries, which makes every rule testable in
isolation. The fallback order is fixed and never blends two sources:

1. local (area-level) reports
2. city-level reports
3. configured seed prices
4. unavailable
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from app.schemas.price import EvidenceQuality, GeographicScope, PriceEstimate
from app.schemas.report import TIER1_COMPLETED_OUTCOMES
from app.services.materials import (
    material_aliases,
    material_label,
    normalize_material,
    normalize_text,
)
from app.services.report_validation import normalize_city

SUPPORTED_UNIT = "kg"
DEFAULT_CURRENCY = "PKR"

_CONFIDENCE_BY_QUALITY: dict[EvidenceQuality, float] = {
    "high": 0.85,
    "medium": 0.65,
    "low": 0.4,
    "none": 0.0,
}


@dataclass(frozen=True)
class PriceObservation:
    """A report-shaped observation after it has been read from storage."""

    report_id: UUID
    picker_id: str
    material: str | None
    price_per_kg: Decimal | None
    quantity_kg: Decimal | None
    currency: str | None
    city: str | None
    area: str | None
    observed_at: datetime | None
    status: str = "accepted"
    is_anomalous: bool = False
    unit: str = SUPPORTED_UNIT
    anomaly_outcome: str = "pass"

    @property
    def normalized_material(self) -> str | None:
        return normalize_material(self.material)


@dataclass(frozen=True)
class SeedPrice:
    """One configured seed reference, already parsed from its JSON file."""

    material: str
    city: str | None
    price_per_kg: Decimal
    currency: str
    source: str
    collected_at: date
    collector: str | None = None
    unit: str = SUPPORTED_UNIT

    @property
    def normalized_material(self) -> str | None:
        return normalize_material(self.material)


@dataclass(frozen=True)
class PriceEvaluation:
    """The public estimate plus internal, non-exposing diagnostics."""

    estimate: PriceEstimate
    excluded: dict[str, int] = field(default_factory=dict)
    duplicate_count: int = 0


@dataclass(frozen=True)
class ObservationSummary:
    """Aggregates for one already-qualified report set."""

    price: Decimal
    minimum: Decimal
    maximum: Decimal
    oldest: datetime
    newest: datetime
    freshness: float
    quality: EvidenceQuality
    confidence: float


def as_utc(value: datetime) -> datetime:
    """Treat naive timestamps as UTC rather than guessing another zone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_currency(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        return None
    return normalized


def eligibility_reason(
    observation: PriceObservation,
    *,
    currency: str = DEFAULT_CURRENCY,
) -> str | None:
    """Return why an observation is ineligible, or ``None`` when it is valid.

    The report schema stores a dedicated ``price_per_kg`` column, so a stored
    report is treated as PKR/kg only when its currency matches the requested
    currency. No unit or currency conversion is attempted.
    """
    if observation.status != "accepted":
        return f"status:{observation.status}"
    if observation.anomaly_outcome not in TIER1_COMPLETED_OUTCOMES:
        return f"anomaly_outcome:{observation.anomaly_outcome}"
    if observation.is_anomalous:
        return "flagged_anomalous"
    if normalize_city(observation.city) is None:
        return "missing_city"
    if observation.unit != SUPPORTED_UNIT:
        return "unit_mismatch"
    if observation.normalized_material is None:
        return "missing_material"
    if observation.price_per_kg is None:
        return "missing_price"
    if not observation.price_per_kg.is_finite() or observation.price_per_kg <= 0:
        return "invalid_price"
    observed_currency = normalize_currency(observation.currency)
    if observed_currency is None:
        return "invalid_currency"
    if observed_currency != currency:
        return "currency_mismatch"
    if observation.observed_at is None:
        return "missing_timestamp"
    return None


def median_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def dedupe_observations(
    observations: list[PriceObservation],
    *,
    window_minutes: int,
) -> tuple[list[PriceObservation], int]:
    """Collapse identical reports submitted by one picker in a short window.

    The database has no idempotency key, so this guard prevents a retried or
    reprocessed message from inflating the evidence count. A window of zero
    disables the guard.
    """
    if window_minutes <= 0:
        return list(observations), 0

    window = timedelta(minutes=window_minutes)
    ordered = sorted(
        (observation for observation in observations if observation.observed_at is not None),
        key=lambda observation: as_utc(cast(datetime, observation.observed_at)),
    )

    last_seen: dict[tuple[object, ...], datetime] = {}
    kept: list[PriceObservation] = []
    duplicates = 0

    for observation in ordered:
        observed_at = as_utc(cast(datetime, observation.observed_at))
        key = (
            observation.picker_id,
            observation.normalized_material,
            observation.price_per_kg,
            observation.quantity_kg,
            normalize_text(observation.city),
            normalize_text(observation.area),
            normalize_currency(observation.currency),
        )
        previous = last_seen.get(key)
        if previous is not None and observed_at - previous <= window:
            duplicates += 1
            continue
        last_seen[key] = observed_at
        kept.append(observation)

    return kept, duplicates


def evidence_quality(
    observation_count: int,
    *,
    freshness_days: float,
    min_observations: int,
) -> EvidenceQuality:
    """Coarse evidence label based on volume and freshness, not price spread."""
    if observation_count < min_observations:
        return "none"
    if observation_count >= min_observations * 2 and freshness_days <= 7:
        return "high"
    if freshness_days <= 30:
        return "medium"
    return "low"


def select_seed_prices(
    seed_prices: list[SeedPrice],
    *,
    aliases: set[str],
    city: str | None,
    currency: str,
    now: datetime,
    max_age_days: int,
) -> list[SeedPrice]:
    """Return only seed entries that are comparable to the request."""
    today = as_utc(now).date()
    cutoff = today - timedelta(days=max_age_days)
    matches: list[SeedPrice] = []

    for entry in seed_prices:
        if entry.unit != SUPPORTED_UNIT:
            continue
        if entry.normalized_material not in aliases:
            continue
        if normalize_currency(entry.currency) != currency:
            continue
        if entry.price_per_kg is None or not entry.price_per_kg.is_finite():
            continue
        if entry.price_per_kg <= 0:
            continue
        if not entry.source.strip():
            continue
        if entry.collected_at > today:
            continue
        if entry.collected_at < cutoff:
            continue

        entry_city = normalize_text(entry.city)
        if city is None:
            if entry_city is not None:
                continue
        elif entry_city != city:
            continue

        matches.append(entry)

    return matches


def _summarize(
    observations: list[PriceObservation],
    *,
    now: datetime,
    min_observations: int,
) -> ObservationSummary:
    prices: list[Decimal] = []
    observed_at: list[datetime] = []
    for observation in observations:
        if observation.price_per_kg is not None:
            prices.append(observation.price_per_kg)
        if observation.observed_at is not None:
            observed_at.append(as_utc(observation.observed_at))

    estimate = median_decimal(prices)
    if estimate is None:
        raise ValueError("cannot summarize observations without prices")
    newest = max(observed_at)
    oldest = min(observed_at)
    freshness = round(max(0.0, (now - newest).total_seconds() / 86400), 1)
    quality = evidence_quality(
        len(observations),
        freshness_days=freshness,
        min_observations=min_observations,
    )

    return ObservationSummary(
        price=estimate,
        minimum=min(prices),
        maximum=max(prices),
        oldest=oldest,
        newest=newest,
        freshness=freshness,
        quality=quality,
        confidence=_CONFIDENCE_BY_QUALITY[quality],
    )


def _report_limitations(duplicate_window_minutes: int) -> list[str]:
    limitations = [
        "The observed range is the range of eligible reports, not a guaranteed market boundary.",
        "Estimates use the median of checked picker reports; flagged or rejected reports "
        "are excluded.",
        "This is a picker-reported reference, not a dealer quote or an exchange price.",
    ]
    if duplicate_window_minutes > 0:
        limitations.append(
            "Identical reports from the same picker within "
            f"{duplicate_window_minutes} minutes are counted once."
        )
    return limitations


def evaluate_price(
    *,
    material: str,
    location: str | None,
    area: str | None,
    observations: list[PriceObservation],
    seed_prices: list[SeedPrice],
    now: datetime,
    currency: str = DEFAULT_CURRENCY,
    min_observations: int = 3,
    max_observation_age_days: int = 90,
    duplicate_window_minutes: int = 15,
) -> PriceEvaluation:
    """Filter observations and apply the local -> city -> seed -> unavailable chain."""
    evaluated_at = as_utc(now)
    normalized_currency = normalize_currency(currency) or DEFAULT_CURRENCY
    canonical_material = normalize_material(material) or material.strip()
    label = material_label(canonical_material)
    aliases = set(material_aliases(material))
    city = normalize_text(location)
    area_name = normalize_text(area)
    area_text = area.strip() if area else "this area"
    cutoff = evaluated_at - timedelta(days=max_observation_age_days)

    excluded: Counter[str] = Counter()
    eligible: list[PriceObservation] = []

    for observation in observations:
        reason = eligibility_reason(observation, currency=normalized_currency)
        if reason is not None:
            excluded[reason] += 1
            continue
        if observation.normalized_material not in aliases:
            excluded["material_mismatch"] += 1
            continue
        if as_utc(cast(datetime, observation.observed_at)) < cutoff:
            excluded["stale"] += 1
            continue
        if city is None:
            excluded["location_missing"] += 1
            continue
        if normalize_text(observation.city) != city:
            excluded["location_mismatch"] += 1
            continue
        eligible.append(observation)

    city_observations, duplicate_count = dedupe_observations(
        eligible,
        window_minutes=duplicate_window_minutes,
    )
    local_observations = (
        [
            observation
            for observation in city_observations
            if normalize_text(observation.area) == area_name
        ]
        if area_name is not None
        else []
    )

    common = {
        "material": canonical_material,
        "material_label": label,
        "location": location,
        "area": area,
        "currency": normalized_currency,
        "local_observation_count": len(local_observations),
        "city_observation_count": len(city_observations),
        "generated_at": evaluated_at,
    }

    if area_name is not None and len(local_observations) >= min_observations:
        summary = _summarize(
            local_observations,
            now=evaluated_at,
            min_observations=min_observations,
        )
        return PriceEvaluation(
            estimate=PriceEstimate(
                **common,
                unit=SUPPORTED_UNIT,
                estimated_price_per_kg=float(summary.price),
                source="local_reports",
                geographic_scope="area",
                observation_count=len(local_observations),
                observed_min_price_per_kg=float(summary.minimum),
                observed_max_price_per_kg=float(summary.maximum),
                oldest_observation_at=summary.oldest,
                newest_observation_at=summary.newest,
                freshness_days=summary.freshness,
                evidence_quality=summary.quality,
                confidence=summary.confidence,
                message=(
                    f"Based on {len(local_observations)} checked picker reports from "
                    f"{area_text}, {location or ''}."
                ).strip(),
                limitations=_report_limitations(duplicate_window_minutes),
            ),
            excluded=dict(excluded),
            duplicate_count=duplicate_count,
        )

    if len(city_observations) >= min_observations:
        summary = _summarize(
            city_observations,
            now=evaluated_at,
            min_observations=min_observations,
        )
        area_note = (
            f" Not enough checked reports from {area_text} alone;"
            if area_name is not None
            else ""
        )
        return PriceEvaluation(
            estimate=PriceEstimate(
                **common,
                unit=SUPPORTED_UNIT,
                estimated_price_per_kg=float(summary.price),
                source="city_reports",
                geographic_scope="city",
                observation_count=len(city_observations),
                observed_min_price_per_kg=float(summary.minimum),
                observed_max_price_per_kg=float(summary.maximum),
                oldest_observation_at=summary.oldest,
                newest_observation_at=summary.newest,
                freshness_days=summary.freshness,
                evidence_quality=summary.quality,
                confidence=summary.confidence,
                message=(
                    f"{area_note} Based on {len(city_observations)} checked picker "
                    f"reports across {location or 'the city'}."
                ).strip(),
                limitations=_report_limitations(duplicate_window_minutes),
            ),
            excluded=dict(excluded),
            duplicate_count=duplicate_count,
        )

    seed_scope: GeographicScope = "city" if city is not None else "national"
    seed_matches = select_seed_prices(
        seed_prices,
        aliases=aliases,
        city=city,
        currency=normalized_currency,
        now=evaluated_at,
        max_age_days=max_observation_age_days,
    )
    if not seed_matches and city is not None:
        seed_matches = select_seed_prices(
            seed_prices,
            aliases=aliases,
            city=None,
            currency=normalized_currency,
            now=evaluated_at,
            max_age_days=max_observation_age_days,
        )
        seed_scope = "national"

    if seed_matches:
        prices = [entry.price_per_kg for entry in seed_matches]
        seed_price = median_decimal(prices)
        if seed_price is None:
            raise ValueError("seed matches must contain prices")
        newest_collected = max(entry.collected_at for entry in seed_matches)
        collected_at = datetime.combine(newest_collected, time.min, tzinfo=UTC)
        freshness = round(max(0.0, (evaluated_at - collected_at).total_seconds() / 86400), 1)
        sources = sorted({entry.source.strip() for entry in seed_matches})

        return PriceEvaluation(
            estimate=PriceEstimate(
                **common,
                unit=SUPPORTED_UNIT,
                estimated_price_per_kg=float(seed_price),
                source="seed_data",
                geographic_scope=seed_scope,
                observation_count=len(seed_matches),
                observed_min_price_per_kg=None,
                observed_max_price_per_kg=None,
                oldest_observation_at=None,
                newest_observation_at=None,
                freshness_days=freshness,
                evidence_quality="low",
                confidence=0.3,
                seed_source="; ".join(sources),
                seed_collected_at=newest_collected,
                message=(
                    "No checked reports met the evidence threshold. This is a seeded "
                    f"{seed_scope} reference for {label}, not live market data."
                ),
                limitations=[
                    "Derived from configured seed entries, not live picker reports.",
                    "Seed references may not reflect current market prices.",
                    "An observed report range is not available for seed references.",
                ],
            ),
            excluded=dict(excluded),
            duplicate_count=duplicate_count,
        )

    reason_text = (
        f"At least {min_observations} checked reports are required for a report-based estimate."
    )
    scope_text = f" in {location.strip()}" if location else ""
    return PriceEvaluation(
        estimate=PriceEstimate(
            **common,
            unit=SUPPORTED_UNIT,
            estimated_price_per_kg=None,
            source="unavailable",
            geographic_scope="none",
            observation_count=0,
            observed_min_price_per_kg=None,
            observed_max_price_per_kg=None,
            oldest_observation_at=None,
            newest_observation_at=None,
            freshness_days=None,
            evidence_quality="none",
            confidence=0.0,
            message=(
                f"No trustworthy price estimate is available for {label}{scope_text}. "
                f"{reason_text}"
            ),
            limitations=[
                "No eligible report evidence or seed reference met the configured requirements.",
                reason_text,
            ],
        ),
        excluded=dict(excluded),
        duplicate_count=duplicate_count,
    )
