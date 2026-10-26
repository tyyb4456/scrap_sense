"""Tier 2 model integration boundary (deliberately disabled).

There is not enough real, comparable report data in this repository to train or
evaluate an Isolation Forest honestly, so no model is trained or enabled here.
This module exposes the interface the pipeline uses and the data-readiness rule
that must be satisfied before a future detector is switched on.

Future feature contract (no identities, no raw text, no precise location):

- ``log1p(price_per_kg)``
- ``log1p(quantity_kg)``

The future training policy is: only accepted, non-anomalous historical reports;
time-based train/validation split; minimum ``ANOMALY_ML_MIN_REPORTS`` rows spread
across at least three materials and two cities; artifact and metadata saved
together; evaluation reported on the held-out period before enabling. Until
then ``evaluate_ml_check`` returns an explicit ``disabled``/``unavailable``
outcome and the workflow continues with deterministic evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.schemas.report import AnomalyVerdict

FEATURE_CONTRACT = ("log1p(price_per_kg)", "log1p(quantity_kg)")
MIN_DISTINCT_MATERIALS = 3
MIN_DISTINCT_CITIES = 2


@dataclass(frozen=True)
class MLReadiness:
    ready: bool
    reason: str
    report_count: int
    distinct_materials: int
    distinct_cities: int


def assess_ml_readiness(
    *,
    report_count: int,
    distinct_materials: int,
    distinct_cities: int,
    min_reports: int,
) -> MLReadiness:
    """Apply the documented data-readiness gate without training a model."""
    if report_count < min_reports:
        return MLReadiness(
            ready=False,
            reason=(
                f"Only {report_count} comparable accepted reports; "
                f"{min_reports} are required before model training is considered."
            ),
            report_count=report_count,
            distinct_materials=distinct_materials,
            distinct_cities=distinct_cities,
        )
    if distinct_materials < MIN_DISTINCT_MATERIALS:
        return MLReadiness(
            ready=False,
            reason=(
                f"Only {distinct_materials} materials represented; "
                f"{MIN_DISTINCT_MATERIALS} are required for a defensible model."
            ),
            report_count=report_count,
            distinct_materials=distinct_materials,
            distinct_cities=distinct_cities,
        )
    if distinct_cities < MIN_DISTINCT_CITIES:
        return MLReadiness(
            ready=False,
            reason=(
                f"Only {distinct_cities} cities represented; "
                f"{MIN_DISTINCT_CITIES} are required for a defensible model."
            ),
            report_count=report_count,
            distinct_materials=distinct_materials,
            distinct_cities=distinct_cities,
        )
    return MLReadiness(
        ready=True,
        reason="The documented data-readiness threshold is satisfied.",
        report_count=report_count,
        distinct_materials=distinct_materials,
        distinct_cities=distinct_cities,
    )


def evaluate_ml_check(settings: Settings) -> AnomalyVerdict:
    """Return the Tier 2 verdict for the current deployment."""
    if not settings.anomaly_ml_enabled:
        return AnomalyVerdict(
            is_anomalous=False,
            reason=(
                "Model-based anomaly detection is disabled until a trained, "
                "evaluated artifact and sufficient real data are available."
            ),
            method="ml",
            confidence=0.0,
            outcome="disabled",
        )

    if not settings.anomaly_ml_artifact_path.exists():
        return AnomalyVerdict(
            is_anomalous=False,
            reason=(
                "Model-based detection is enabled but the trained artifact is "
                "missing; deterministic evidence is used instead."
            ),
            method="ml",
            confidence=0.0,
            outcome="unavailable",
        )

    return AnomalyVerdict(
        is_anomalous=False,
        reason=(
            "An artifact path is configured, but this release does not register a "
            "compatible detector loader; deterministic evidence is used instead."
        ),
        method="ml",
        confidence=0.0,
        outcome="unavailable",
    )
