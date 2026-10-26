from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.schemas.report import ReportDraft
from app.services.report_validation import (
    clarification_question,
    validate_report_draft,
)

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


DRAFT_VALUES: dict[str, object] = {
    "material": "plastic",
    "price_per_kg": Decimal("150"),
    "quantity_kg": Decimal("2"),
    "currency": "PKR",
    "unit": "kg",
    "city": "Multan",
    "area": "Shah Rizwan",
    "observed_at": NOW - timedelta(hours=2),
    "confidence": None,
    "needs_clarification": False,
    "clarification_question": None,
}


def valid_draft(**overrides: object) -> ReportDraft:
    values = {**DRAFT_VALUES, **overrides}
    return ReportDraft(**values)  # type: ignore[arg-type]


def constructed_draft(**overrides: object) -> ReportDraft:
    values = {**DRAFT_VALUES, **overrides}
    return ReportDraft.model_construct(**values)  # type: ignore[arg-type]


def test_valid_report_passes() -> None:
    result = validate_report_draft(valid_draft(), now=NOW)

    assert result.is_valid is True
    assert result.issues == []


def test_missing_required_fields_are_reported_without_raw_text() -> None:
    result = validate_report_draft(None, now=NOW)
    assert result.is_valid is False
    assert "missing_report" in result.codes

    result = validate_report_draft(ReportDraft(), now=NOW)
    assert result.is_valid is False
    assert {"missing_material", "missing_price", "missing_quantity"} <= result.codes
    question = clarification_question(result, ReportDraft())
    assert "price per kg" in question
    assert "quantity in kg" in question


def test_unknown_material_is_not_silently_accepted() -> None:
    result = validate_report_draft(valid_draft(material="unobtainium"), now=NOW)

    assert result.is_valid is False
    assert "unsupported_material" in result.codes


def test_zero_and_negative_prices_are_invalid() -> None:
    for price in (Decimal("0"), Decimal("-1")):
        result = validate_report_draft(valid_draft(price_per_kg=price), now=NOW)
        assert result.is_valid is False
        assert "invalid_price" in result.codes


def test_non_finite_prices_and_quantities_are_invalid() -> None:
    for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        result = validate_report_draft(
            constructed_draft(price_per_kg=value),
            now=NOW,
        )
        assert result.is_valid is False
        assert "non_finite_price" in result.codes

        result = validate_report_draft(
            constructed_draft(quantity_kg=value),
            now=NOW,
        )
        assert result.is_valid is False
        assert "non_finite_quantity" in result.codes


def test_invalid_currency_and_unit_are_rejected() -> None:
    currency = validate_report_draft(valid_draft(currency="US"), now=NOW)
    assert "invalid_currency" in currency.codes

    unsupported = validate_report_draft(valid_draft(currency="USD"), now=NOW)
    assert "unsupported_currency" in unsupported.codes

    unit = validate_report_draft(valid_draft(unit="lb"), now=NOW)
    assert "unsupported_unit" in unit.codes


def test_area_without_city_is_inconsistent() -> None:
    result = validate_report_draft(valid_draft(city=None, area="Shah Rizwan"), now=NOW)

    assert result.is_valid is False
    assert "location_inconsistent" in result.codes


def test_future_timestamp_is_invalid() -> None:
    result = validate_report_draft(
        valid_draft(observed_at=NOW + timedelta(days=2)),
        now=NOW,
    )

    assert result.is_valid is False
    assert "future_timestamp" in result.codes


def test_unparseable_timestamp_is_invalid() -> None:
    draft = constructed_draft(observed_at="not-a-date")

    result = validate_report_draft(draft, now=NOW)

    assert result.is_valid is False
    assert "invalid_timestamp" in result.codes
