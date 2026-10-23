from app.schemas.price import PriceEstimate
from app.tools.price_estimator import estimate_price


def test_estimate_price_returns_the_seed_placeholder_contract() -> None:
    estimate = PriceEstimate.model_validate(estimate_price("plastic", "Multan"))

    assert estimate.material_type == "plastic"
    assert estimate.location == "Multan"
    assert estimate.estimated_price_per_kg == 0.0
    assert estimate.confidence == 0.0
    assert estimate.tier_used == "seed"
    assert estimate.local_report_count == 0
    assert estimate.city_report_count == 0
