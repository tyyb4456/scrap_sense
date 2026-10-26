from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.anomaly_detection import (
    AnomalyPolicy,
    evaluate_statistical_anomaly,
)
from app.services.price_aggregation import PriceObservation

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)
POLICY = AnomalyPolicy()


def observation(
    *,
    price: str = "100",
    material: str = "plastic",
    currency: str = "PKR",
    city: str = "Multan",
    area: str = "Shah Rizwan",
    unit: str = "kg",
    status: str = "accepted",
    is_anomalous: bool = False,
    observed_at: datetime | None = None,
) -> PriceObservation:
    return PriceObservation(
        report_id=uuid.uuid4(),
        picker_id=f"picker-{uuid.uuid4()}",
        material=material,
        price_per_kg=Decimal(price),
        quantity_kg=Decimal("2"),
        currency=currency,
        city=city,
        area=area,
        observed_at=observed_at or (NOW - timedelta(days=1)),
        status=status,
        is_anomalous=is_anomalous,
        unit=unit,
    )


def evaluate(
    observations: list[PriceObservation],
    *,
    price: str = "100",
    material: str = "plastic",
    currency: str = "PKR",
    city: str | None = "Multan",
    area: str | None = "Shah Rizwan",
    unit: str = "kg",
    policy: AnomalyPolicy = POLICY,
):
    return evaluate_statistical_anomaly(
        material=material,
        price_per_kg=Decimal(price),
        currency=currency,
        city=city,
        area=area,
        unit=unit,
        observations=observations,
        now=NOW,
        policy=policy,
    )


def ordinary_sample() -> list[PriceObservation]:
    return [
        observation(price="100"),
        observation(price="105"),
        observation(price="95"),
        observation(price="110"),
        observation(price="90"),
        observation(price="102"),
    ]


def test_ordinary_variation_is_not_flagged() -> None:
    result = evaluate(ordinary_sample(), price="112")

    assert result.is_anomalous is False
    assert result.outcome == "pass"
    assert result.method == "mad"
    assert result.sample_size == 6


def test_clear_outlier_is_marked_suspicious_not_rejected() -> None:
    result = evaluate(ordinary_sample(), price="1000")

    assert result.is_anomalous is True
    assert result.outcome == "suspicious"
    assert result.confidence > 0.6
    assert "statistical outlier" in result.reason.lower()


def test_thresholds_are_configurable() -> None:
    lenient = AnomalyPolicy(mad_z_threshold=1000.0)
    result = evaluate(ordinary_sample(), price="1000", policy=lenient)

    assert result.is_anomalous is False
    assert result.outcome == "pass"


def test_small_sample_returns_insufficient_evidence() -> None:
    result = evaluate(ordinary_sample()[:3], price="1000")

    assert result.is_anomalous is False
    assert result.outcome == "insufficient_evidence"
    assert result.confidence == 0.0


def test_no_history_returns_insufficient_evidence() -> None:
    result = evaluate([], price="100")

    assert result.outcome == "insufficient_evidence"


def test_identical_observations_with_matching_price_pass() -> None:
    result = evaluate([observation(price="100") for _ in range(5)], price="100")

    assert result.is_anomalous is False
    assert result.outcome == "pass"
    assert result.mad_price_per_kg == Decimal("0")


def test_zero_mad_extreme_value_is_suspicious() -> None:
    result = evaluate([observation(price="100") for _ in range(5)], price="250")

    assert result.is_anomalous is True
    assert result.outcome == "suspicious"
    assert result.mad_price_per_kg == Decimal("0")


def test_zero_mad_small_deviation_is_insufficient_not_invented() -> None:
    result = evaluate([observation(price="100") for _ in range(5)], price="110")

    assert result.is_anomalous is False
    assert result.outcome == "insufficient_evidence"


def test_material_mismatch_is_not_compared() -> None:
    copper = [observation(price="900", material="copper") for _ in range(5)]
    result = evaluate(copper, price="100", material="plastic")

    assert result.outcome == "insufficient_evidence"
    assert result.sample_size == 0


def test_currency_mismatch_is_not_compared() -> None:
    usd = [observation(price="100", currency="USD") for _ in range(5)]
    result = evaluate(usd, price="100", currency="PKR")

    assert result.outcome == "insufficient_evidence"


def test_unit_mismatch_is_not_compared() -> None:
    per_item = [observation(price="100", unit="item") for _ in range(5)]
    result = evaluate(per_item, price="100")

    assert result.outcome == "insufficient_evidence"


def test_city_mismatch_is_not_compared() -> None:
    lahore = [observation(price="100", city="Lahore") for _ in range(5)]
    result = evaluate(lahore, price="100", city="Multan")

    assert result.outcome == "insufficient_evidence"


def test_stale_observations_are_not_compared() -> None:
    stale = [
        observation(price="100", observed_at=NOW - timedelta(days=200))
        for _ in range(5)
    ]
    result = evaluate(stale, price="100")

    assert result.outcome == "insufficient_evidence"


def test_flagged_history_is_not_used_as_a_baseline() -> None:
    flagged = [
        observation(price="100", status="flagged"),
        observation(price="100", is_anomalous=True),
        observation(price="100"),
        observation(price="100"),
        observation(price="100"),
    ]
    result = evaluate(flagged, price="100")

    assert result.outcome == "insufficient_evidence"
    assert result.sample_size == 0


def test_area_scope_is_used_when_it_has_enough_evidence() -> None:
    observations = [
        observation(price="100", area="A"),
        observation(price="101", area="A"),
        observation(price="99", area="A"),
        observation(price="102", area="A"),
        observation(price="98", area="A"),
        observation(price="300", area="B"),
        observation(price="300", area="B"),
        observation(price="300", area="B"),
        observation(price="300", area="B"),
        observation(price="300", area="B"),
    ]
    result = evaluate(observations, price="100", area="A")

    assert result.outcome == "pass"
    assert result.sample_size == 5
    assert "area-level" in result.reason


def test_missing_city_or_invalid_candidate_is_insufficient() -> None:
    sample = ordinary_sample()
    assert evaluate(sample, city=None).outcome == "insufficient_evidence"
    assert evaluate(sample, unit="item").outcome == "insufficient_evidence"
    assert evaluate(sample, price="0").outcome == "insufficient_evidence"
