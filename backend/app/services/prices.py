"""Database-backed price estimation service."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BACKEND_DIR, Settings
from app.models.report import Report
from app.schemas.price import PriceEstimate, SeedPriceFile
from app.services.materials import material_aliases, normalize_material, normalize_text
from app.services.price_aggregation import (
    DEFAULT_CURRENCY,
    PriceEvaluation,
    PriceObservation,
    SeedPrice,
    as_utc,
    evaluate_price,
    normalize_currency,
)
from app.services.reports import fetch_reports_for_pricing

logger = logging.getLogger(__name__)


def resolve_seed_path(path: Path) -> Path:
    """Resolve a relative seed path against the backend directory."""
    return path if path.is_absolute() else BACKEND_DIR / path


def load_seed_prices(settings: Settings) -> list[SeedPrice]:
    """Load configured seed entries, failing closed on a malformed file."""
    path = resolve_seed_path(settings.price_seed_prices_path)
    if not path.exists():
        logger.debug("No seed price file at %s", path)
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        file = SeedPriceFile.model_validate(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError):
        logger.warning("Ignoring unreadable or invalid seed price file at %s", path)
        return []
    if file.schema_version != 1:
        logger.warning(
            "Ignoring unsupported seed price schema_version=%s at %s",
            file.schema_version,
            path,
        )
        return []

    entries: list[SeedPrice] = []
    for entry in file.entries:
        entries.append(
            SeedPrice(
                material=entry.material,
                city=entry.city,
                price_per_kg=entry.price_per_kg,
                currency=normalize_currency(entry.currency) or entry.currency,
                source=entry.source,
                collected_at=entry.collected_at,
                collector=entry.collector,
                unit=entry.unit,
            )
        )
    return entries


def observation_from_report(report: Report) -> PriceObservation:
    observed_at = report.effective_observed_at
    return PriceObservation(
        report_id=report.id,
        picker_id=report.picker_id,
        material=report.material,
        price_per_kg=report.price_per_kg,
        quantity_kg=report.quantity_kg,
        currency=report.currency,
        city=report.city,
        area=report.area,
        observed_at=as_utc(observed_at) if observed_at is not None else None,
        status=report.status,
        is_anomalous=report.is_anomalous,
        unit="kg",
        anomaly_outcome="suspicious" if report.is_anomalous else "pass",
    )


class PriceService:
    """Read eligible reports and return a deterministic price estimate."""

    def __init__(self, *, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def estimate(
        self,
        *,
        material: str,
        location: str | None = None,
        area: str | None = None,
        now: datetime | None = None,
    ) -> PriceEstimate:
        evaluated_at = as_utc(now or datetime.now(UTC))
        city = normalize_text(location)
        observations: list[PriceObservation] = []

        if city is not None:
            since = evaluated_at - timedelta(
                days=self._settings.price_max_observation_age_days
            )
            reports = await fetch_reports_for_pricing(
                self._session,
                material_aliases=set(material_aliases(material)),
                city=city,
                currency=DEFAULT_CURRENCY,
                since=since,
                limit=self._settings.price_max_observations,
            )
            observations = [observation_from_report(report) for report in reports]

        evaluation = evaluate_price(
            material=material,
            location=location,
            area=area,
            observations=observations,
            seed_prices=load_seed_prices(self._settings),
            now=evaluated_at,
            currency=DEFAULT_CURRENCY,
            min_observations=self._settings.price_min_observations,
            max_observation_age_days=self._settings.price_max_observation_age_days,
            duplicate_window_minutes=self._settings.price_duplicate_window_minutes,
        )
        self._log_diagnostics(evaluation, material=material, city=city)
        return evaluation.estimate

    def _log_diagnostics(
        self,
        evaluation: PriceEvaluation,
        *,
        material: str,
        city: str | None,
    ) -> None:
        if not evaluation.excluded and evaluation.duplicate_count == 0:
            return
        # Counts only: never log raw report text, picker ids, or contact details.
        logger.info(
            "Price evidence excluded for material=%s city=%s: %s; duplicates=%d",
            normalize_material(material),
            city,
            evaluation.excluded,
            evaluation.duplicate_count,
        )
