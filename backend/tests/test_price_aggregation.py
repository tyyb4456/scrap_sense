from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.services.materials import material_aliases, material_label, normalize_material
from app.services.price_aggregation import (
    PriceObservation,
    SeedPrice,
    eligibility_reason,
    evaluate_price,
    median_decimal,
)

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


def observation(
    *,
    price: str | None = "150",
    material: str | None = "plastic",
    city: str | None = "Multan",
    area: str | None = "Shah Rizwan",
    picker_id: str | None = None,
    observed_at: datetime | None = None,
    currency: str | None = "PKR",
    unit: str = "kg",
    status: str = "accepted",
    is_anomalous: bool = False,
    quantity: str | None = "2",
    anomaly_outcome: str = "pass",
    reviewed_at: datetime | None = None,
) -> PriceObservation:
    return PriceObservation(
        report_id=uuid.uuid4(),
        picker_id=picker_id or f"picker-{uuid.uuid4()}",
        material=material,
        price_per_kg=Decimal(price) if price is not None else None,
        quantity_kg=Decimal(quantity) if quantity is not None else None,
        currency=currency,
        city=city,
        area=area,
        observed_at=observed_at or (NOW - timedelta(days=1)),
        status=status,
        is_anomalous=is_anomalous,
        unit=unit,
        anomaly_outcome=anomaly_outcome,
        reviewed_at=reviewed_at,
    )


def seed(
    *,
    price: str = "180",
    material: str = "plastic",
    city: str | None = "Multan",
    currency: str = "PKR",
    collected_at: Any = None,
    source: str = "Week 1 field collection",
    unit: str = "kg",
) -> SeedPrice:
    return SeedPrice(
        material=material,
        city=city,
        price_per_kg=Decimal(price),
        currency=currency,
        source=source,
        collected_at=collected_at or (NOW.date() - timedelta(days=2)),
        unit=unit,
    )


def evaluate(
    observations: list[PriceObservation],
    *,
    seeds: list[SeedPrice] | None = None,
    material: str = "plastic",
    location: str | None = "Multan",
    area: str | None = "Shah Rizwan",
    min_observations: int = 3,
    max_age_days: int = 90,
    duplicate_window_minutes: int = 15,
):
    return evaluate_price(
        material=material,
        location=location,
        area=area,
        observations=observations,
        seed_prices=seeds or [],
        now=NOW,
        min_observations=min_observations,
        max_observation_age_days=max_age_days,
        duplicate_window_minutes=duplicate_window_minutes,
    )


def test_median_decimal_odd_and_even() -> None:
    assert median_decimal([Decimal("300"), Decimal("100"), Decimal("200")]) == Decimal("200")
    assert median_decimal(
        [Decimal("400"), Decimal("100"), Decimal("300"), Decimal("200")]
    ) == Decimal("250")
    assert median_decimal([]) is None


def test_material_aliases_are_explicit_and_not_substrings() -> None:
    assert normalize_material("Kaghaz") == "paper"
    assert normalize_material("pet bottles") == "plastic"
    assert normalize_material("tamba") == "copper"
    assert material_label("kaghaz") == "Paper"
    assert normalize_material("plastic bag") == "plastic bag"
    assert "plastic bag" not in material_aliases("plastic")
    assert "paper bag" not in material_aliases("paper")


def test_single_observation_is_used_when_threshold_is_one() -> None:
    result = evaluate([observation(price="150")], min_observations=1).estimate

    assert result.source == "local_reports"
    assert result.estimated_price_per_kg == 150.0
    assert result.observation_count == 1
    assert result.local_observation_count == 1
    assert result.city_observation_count == 1
    assert result.geographic_scope == "area"


def test_multiple_observations_use_median_and_observed_range() -> None:
    result = evaluate(
        [
            observation(price="100"),
            observation(price="200"),
            observation(price="300"),
        ]
    ).estimate

    assert result.source == "local_reports"
    assert result.estimated_price_per_kg == 200.0
    assert result.observed_min_price_per_kg == 100.0
    assert result.observed_max_price_per_kg == 300.0
    assert result.observation_count == 3


def test_invalid_and_missing_prices_are_excluded() -> None:
    evaluation = evaluate(
        [
            observation(price=None),
            observation(price="0"),
            observation(price="-5"),
            observation(price="100"),
            observation(price="200"),
            observation(price="300"),
        ]
    )

    result = evaluation.estimate
    assert result.source == "local_reports"
    assert result.observation_count == 3
    assert evaluation.excluded["missing_price"] == 1
    assert evaluation.excluded["invalid_price"] == 2


def test_material_mismatch_is_excluded() -> None:
    evaluation = evaluate(
        [
            observation(material="copper"),
            observation(material="copper"),
            observation(material="copper"),
        ]
    )

    assert evaluation.estimate.source == "unavailable"
    assert evaluation.estimate.estimated_price_per_kg is None
    assert evaluation.excluded["material_mismatch"] == 3


def test_unit_mismatch_is_excluded() -> None:
    evaluation = evaluate(
        [
            observation(unit="item"),
            observation(unit="item"),
            observation(unit="item"),
        ]
    )

    assert evaluation.estimate.source == "unavailable"
    assert evaluation.excluded["unit_mismatch"] == 3


def test_currency_mismatch_is_excluded() -> None:
    evaluation = evaluate(
        [
            observation(currency="USD"),
            observation(currency="USD"),
            observation(currency="USD"),
        ]
    )

    assert evaluation.estimate.source == "unavailable"
    assert evaluation.excluded["currency_mismatch"] == 3


def test_empty_observations_return_unavailable_not_zero() -> None:
    result = evaluate([]).estimate

    assert result.source == "unavailable"
    assert result.estimated_price_per_kg is None
    assert result.observation_count == 0
    assert result.confidence == 0.0
    assert result.evidence_quality == "none"


def test_geographic_filtering_prefers_area_then_city() -> None:
    observations = [
        observation(price="100", area="Shah Rizwan"),
        observation(price="200", area="Shah Rizwan"),
        observation(price="300", area="Shah Rizwan"),
        observation(price="400", area="Gulgasht"),
        observation(price="500", area="Gulgasht"),
    ]

    local = evaluate(observations, area="Shah Rizwan").estimate
    assert local.source == "local_reports"
    assert local.geographic_scope == "area"
    assert local.observation_count == 3
    assert local.estimated_price_per_kg == 200.0

    city = evaluate(observations, area="Gulgasht").estimate
    assert city.source == "city_reports"
    assert city.geographic_scope == "city"
    assert city.observation_count == 5
    assert city.estimated_price_per_kg == 300.0
    assert "Not enough checked reports" in city.message

    unknown_area = evaluate(observations, area="Unknown").estimate
    assert unknown_area.source == "city_reports"
    assert unknown_area.observation_count == 5


def test_missing_location_does_not_mix_markets() -> None:
    evaluation = evaluate(
        [
            observation(city="Multan"),
            observation(city="Multan"),
            observation(city="Multan"),
        ],
        location=None,
        area=None,
    )

    assert evaluation.estimate.source == "unavailable"
    assert evaluation.excluded["location_missing"] == 3


def test_cityless_historical_observations_are_never_eligible() -> None:
    for city in (None, "", "   ", "unknown"):
        evaluation = evaluate(
            [
                observation(city=city, price="100"),
                observation(city=city, price="200"),
                observation(city=city, price="9000"),
            ]
        )

        assert evaluation.estimate.source == "unavailable"
        assert evaluation.estimate.estimated_price_per_kg is None
        assert evaluation.excluded["missing_city"] == 3


def test_cityless_observations_cannot_lower_a_city_estimate() -> None:
    evaluation = evaluate(
        [
            observation(city=None, price="1"),
            observation(city="Multan", price="100"),
            observation(city="Multan", price="200"),
            observation(city="Multan", price="300"),
        ]
    )

    assert evaluation.estimate.source == "local_reports"
    assert evaluation.estimate.estimated_price_per_kg == 200.0
    assert evaluation.estimate.observation_count == 3
    assert evaluation.excluded["missing_city"] == 1


def test_insufficient_evidence_returns_unavailable() -> None:
    result = evaluate([observation(), observation()]).estimate

    assert result.source == "unavailable"
    assert result.city_observation_count == 2
    assert result.estimated_price_per_kg is None
    assert "At least 3 checked reports" in result.message


def test_stale_observations_are_excluded() -> None:
    old = NOW - timedelta(days=100)
    evaluation = evaluate(
        [
            observation(observed_at=old),
            observation(observed_at=old),
            observation(observed_at=old),
        ]
    )

    assert evaluation.estimate.source == "unavailable"
    assert evaluation.excluded["stale"] == 3

    fresh = evaluate(
        [
            observation(observed_at=NOW - timedelta(days=2)),
            observation(observed_at=NOW - timedelta(days=2)),
            observation(observed_at=NOW - timedelta(days=2)),
        ]
    ).estimate
    assert fresh.source == "local_reports"
    assert fresh.freshness_days == 2.0


def test_duplicate_reports_are_counted_once() -> None:
    duplicated = [
        observation(
            price="150",
            picker_id="picker-1",
            observed_at=NOW - timedelta(minutes=5),
            quantity="2",
        ),
        observation(
            price="150",
            picker_id="picker-1",
            observed_at=NOW - timedelta(minutes=4),
            quantity="2",
        ),
        observation(
            price="150",
            picker_id="picker-1",
            observed_at=NOW - timedelta(minutes=3),
            quantity="2",
        ),
    ]

    evaluation = evaluate(duplicated)
    assert evaluation.estimate.source == "unavailable"
    assert evaluation.estimate.city_observation_count == 1
    assert evaluation.duplicate_count == 2

    no_dedupe = evaluate(duplicated, duplicate_window_minutes=0).estimate
    assert no_dedupe.source == "local_reports"
    assert no_dedupe.observation_count == 3


def test_flagged_and_rejected_reports_are_ineligible() -> None:
    assert eligibility_reason(observation()) is None
    assert eligibility_reason(observation(status="flagged")) == "status:flagged"
    assert eligibility_reason(observation(status="rejected")) == "status:rejected"
    assert eligibility_reason(observation(is_anomalous=True)) == "flagged_anomalous"

    evaluation = evaluate(
        [
            observation(status="flagged"),
            observation(status="rejected"),
            observation(is_anomalous=True),
        ]
    )
    assert evaluation.estimate.source == "unavailable"
    assert evaluation.excluded["status:flagged"] == 1
    assert evaluation.excluded["status:rejected"] == 1
    assert evaluation.excluded["flagged_anomalous"] == 1


def test_unverified_outcomes_are_ineligible_for_pricing() -> None:
    assert (
        eligibility_reason(observation(anomaly_outcome="unknown"))
        == "anomaly_outcome:unknown"
    )
    assert (
        eligibility_reason(
            observation(
                status="pending_evidence",
                anomaly_outcome="insufficient_evidence",
            )
        )
        == "status:pending_evidence"
    )
    assert (
        eligibility_reason(observation(anomaly_outcome="insufficient_evidence"))
        == "anomaly_outcome:insufficient_evidence"
    )
    assert (
        eligibility_reason(observation(anomaly_outcome="unavailable"))
        == "anomaly_outcome:unavailable"
    )


def test_reviewer_approved_suspicious_observation_remains_eligible() -> None:
    approved = observation(
        anomaly_outcome="suspicious",
        is_anomalous=False,
        reviewed_at=NOW,
    )

    assert eligibility_reason(approved) is None

    result = evaluate([approved, observation(price="200"), observation(price="300")]).estimate
    assert result.source == "local_reports"
    assert result.observation_count == 3


def test_outliers_are_not_removed() -> None:
    result = evaluate(
        [
            observation(price="100"),
            observation(price="200"),
            observation(price="1000"),
        ]
    ).estimate

    assert result.estimated_price_per_kg == 200.0
    assert result.observed_min_price_per_kg == 100.0
    assert result.observed_max_price_per_kg == 1000.0
    assert result.observation_count == 3


def test_local_reports_take_priority_over_seed_data() -> None:
    result = evaluate(
        [observation(price="150"), observation(price="150"), observation(price="150")],
        seeds=[seed(price="999")],
    ).estimate

    assert result.source == "local_reports"
    assert result.estimated_price_per_kg == 150.0


def test_seed_data_is_used_only_when_reports_are_insufficient() -> None:
    result = evaluate(
        [observation()],
        seeds=[seed(price="180", source="Dealer A field visit")],
    ).estimate

    assert result.source == "seed_data"
    assert result.estimated_price_per_kg == 180.0
    assert result.observation_count == 1
    assert result.seed_source == "Dealer A field visit"
    assert result.seed_collected_at == NOW.date() - timedelta(days=2)
    assert result.evidence_quality == "low"
    assert result.confidence == 0.3
    assert result.observed_min_price_per_kg is None


def test_national_seed_is_used_when_no_location_is_requested() -> None:
    result = evaluate(
        [],
        location=None,
        area=None,
        seeds=[seed(city=None, price="175", source="National reference")],
    ).estimate

    assert result.source == "seed_data"
    assert result.geographic_scope == "national"
    assert result.estimated_price_per_kg == 175.0


def test_national_seed_is_used_when_city_reports_are_insufficient() -> None:
    result = evaluate(
        [observation()],
        seeds=[seed(city=None, price="175", source="National reference")],
    ).estimate

    assert result.source == "seed_data"
    assert result.geographic_scope == "national"
    assert result.estimated_price_per_kg == 175.0
    assert "national reference" in result.message


def test_city_seed_takes_priority_over_national_seed() -> None:
    result = evaluate(
        [],
        seeds=[
            seed(city="Multan", price="180", source="Multan reference"),
            seed(city=None, price="999", source="National reference"),
        ],
    ).estimate

    assert result.source == "seed_data"
    assert result.geographic_scope == "city"
    assert result.estimated_price_per_kg == 180.0


def test_seed_data_with_wrong_city_currency_unit_or_age_is_not_used() -> None:
    result = evaluate(
        [],
        seeds=[
            seed(city="Lahore"),
            seed(currency="USD"),
            seed(unit="item"),
            seed(collected_at=NOW.date() - timedelta(days=400)),
        ],
    ).estimate

    assert result.source == "unavailable"
    assert result.estimated_price_per_kg is None


def test_city_report_source_label_and_counts() -> None:
    result = evaluate(
        [
            observation(area="Other", price="100"),
            observation(area="Other", price="200"),
            observation(area="Other", price="300"),
        ],
        area="Shah Rizwan",
    ).estimate

    assert result.source == "city_reports"
    assert result.local_observation_count == 0
    assert result.city_observation_count == 3
    assert result.observation_count == 3
    assert result.evidence_quality == "medium"
