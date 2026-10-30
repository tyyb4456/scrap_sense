"""Deterministic intake validation.

This module is intentionally separate from statistical anomaly detection. An
invalid report is a data problem, not an unusual price: it must never be sent
to an LLM judge or treated as a suspicious market observation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.schemas.report import ReportDraft
from app.services.materials import MATERIAL_ALIASES, normalize_material, normalize_text

SUPPORTED_CURRENCIES = frozenset({"PKR"})
SUPPORTED_UNITS = frozenset({"kg"})
MAX_PRICE_PER_KG = Decimal("9999999999.99")
MAX_QUANTITY_KG = Decimal("999999999.999")
MAX_FUTURE_HOURS = 24

# Extractions sometimes return a non-answer instead of null. These are not
# cities and must not make a report eligible for the city-based pricing path.
AMBIGUOUS_CITY_VALUES = frozenset(
    {
        "unknown",
        "unknown city",
        "city unknown",
        "not known",
        "not sure",
        "unclear",
        "unspecified",
        "not specified",
        "not stated",
        "not mentioned",
        "not provided",
        "not available",
        "no city",
        "city not stated",
        "somewhere",
        "anywhere",
        "any city",
        "n/a",
        "na",
        "none",
        "null",
        "maybe",
    }
)


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)
    needs_clarification: bool = False

    @property
    def is_valid(self) -> bool:
        return not self.issues

    @property
    def codes(self) -> set[str]:
        return {issue.code for issue in self.issues}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _finite_decimal(value: Decimal | None) -> bool:
    return value is not None and isinstance(value, Decimal) and value.is_finite()


def normalize_city(value: str | None) -> str | None:
    """Return a usable city name, or ``None`` for blank/non-answer values."""
    normalized = normalize_text(value)
    if normalized is None or normalized in AMBIGUOUS_CITY_VALUES:
        return None
    return normalized


def validate_report_draft(
    draft: ReportDraft | None,
    *,
    now: datetime | None = None,
) -> ValidationResult:
    """Return every structural problem with an extracted report.

    The rules here mirror the persisted schema and the supported market surface:
    canonical material names, PKR, kilograms, a positive finite price and
    quantity, coherent location fields, and a plausible sale time.
    """
    if draft is None:
        return ValidationResult(
            issues=[ValidationIssue("report", "missing_report", "the sale details")],
            needs_clarification=True,
        )

    issues: list[ValidationIssue] = []

    material = normalize_material(draft.material)
    if material is None:
        issues.append(ValidationIssue("material", "missing_material", "the material"))
    elif material not in MATERIAL_ALIASES:
        issues.append(
            ValidationIssue(
                "material",
                "unsupported_material",
                "a supported material name",
            )
        )

    if draft.price_per_kg is None:
        issues.append(ValidationIssue("price_per_kg", "missing_price", "the price per kg"))
    elif not _finite_decimal(draft.price_per_kg):
        issues.append(
            ValidationIssue(
                "price_per_kg",
                "non_finite_price",
                "a finite price per kg (not NaN or infinity)",
            )
        )
    elif draft.price_per_kg <= 0:
        issues.append(
            ValidationIssue("price_per_kg", "invalid_price", "a price per kg greater than zero")
        )
    elif draft.price_per_kg > MAX_PRICE_PER_KG:
        issues.append(
            ValidationIssue("price_per_kg", "price_too_large", "a realistic price per kg")
        )

    if draft.quantity_kg is None:
        issues.append(
            ValidationIssue("quantity_kg", "missing_quantity", "the quantity in kg")
        )
    elif not _finite_decimal(draft.quantity_kg):
        issues.append(
            ValidationIssue(
                "quantity_kg",
                "non_finite_quantity",
                "a finite quantity in kg (not NaN or infinity)",
            )
        )
    elif draft.quantity_kg <= 0:
        issues.append(
            ValidationIssue(
                "quantity_kg",
                "invalid_quantity",
                "a quantity greater than zero",
            )
        )
    elif draft.quantity_kg > MAX_QUANTITY_KG:
        issues.append(
            ValidationIssue("quantity_kg", "quantity_too_large", "a realistic quantity in kg")
        )

    currency = (draft.currency or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        issues.append(
            ValidationIssue("currency", "invalid_currency", "a three-letter currency")
        )
    elif currency not in SUPPORTED_CURRENCIES:
        issues.append(
            ValidationIssue(
                "currency",
                "unsupported_currency",
                f"a supported currency ({', '.join(sorted(SUPPORTED_CURRENCIES))})",
            )
        )

    unit = (draft.unit or "").strip().lower()
    if unit not in SUPPORTED_UNITS:
        issues.append(
            ValidationIssue(
                "unit",
                "unsupported_unit",
                f"a supported unit ({', '.join(sorted(SUPPORTED_UNITS))})",
            )
        )

    city = normalize_city(draft.city)
    area = normalize_text(draft.area)
    if city is None:
        issues.append(
            ValidationIssue(
                "city",
                "missing_city",
                "the city where the sale happened",
            )
        )
    if area is not None and city is None:
        issues.append(
            ValidationIssue(
                "location",
                "location_inconsistent",
                "a city when an area is supplied",
            )
        )

    if draft.observed_at is not None:
        try:
            observed_at = _as_utc(draft.observed_at)
        except (AttributeError, TypeError, ValueError, OverflowError):
            issues.append(
                ValidationIssue("observed_at", "invalid_timestamp", "a valid sale time")
            )
        else:
            if observed_at > _as_utc(now or datetime.now(UTC)) + timedelta(
                hours=MAX_FUTURE_HOURS
            ):
                issues.append(
                    ValidationIssue(
                        "observed_at",
                        "future_timestamp",
                        "a sale time that is not in the future",
                    )
                )

    if draft.needs_clarification and not issues:
        issues.append(
            ValidationIssue(
                "report",
                "clarification_required",
                "the missing sale details",
            )
        )

    return ValidationResult(issues=issues, needs_clarification=bool(issues))


GENERIC_CLARIFICATION_CODES = frozenset(
    {
        "missing_city",
        "missing_material",
        "missing_price",
        "missing_quantity",
        "missing_report",
        "clarification_required",
    }
)


def clarification_question(result: ValidationResult, draft: ReportDraft | None = None) -> str:
    """Build a short, picker-facing question without leaking internal details.

    The extractor's own wording is only reused for ordinary missing details. A
    specific structural problem (unsupported currency/unit, impossible value,
    future timestamp) gets the deterministic explanation instead.
    """
    if not result.issues:
        return "Could you clarify the sale details?"
    if (
        draft is not None
        and draft.clarification_question
        and result.codes <= GENERIC_CLARIFICATION_CODES
    ):
        return draft.clarification_question

    missing = [
        issue.message
        for issue in result.issues
        if issue.code in GENERIC_CLARIFICATION_CODES
    ]
    if missing:
        return f"Please provide {_join_phrases(missing)}."
    return f"Please provide {result.issues[0].message}."


def _join_phrases(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"
