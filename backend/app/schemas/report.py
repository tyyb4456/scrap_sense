"""
Pydantic models and schemas for scrap sale reports, extraction, and anomaly verdicts.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AnomalyOutcome = Literal[
    "pass",
    "suspicious",
    "insufficient_evidence",
    "unavailable",
    "disabled",
    "error",
]

ReportStatus = Literal["accepted", "flagged", "rejected"]


class ReportDraft(BaseModel):
    """Structured extraction; semantic validity is decided by validation code.

    Numeric and currency/unit constraints are deliberately permissive here so a
    malformed extraction reaches :mod:`app.services.report_validation` and gets
    a specific clarification question instead of an opaque provider error.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    material: str | None = Field(default=None, max_length=100)
    price_per_kg: Decimal | None = None
    quantity_kg: Decimal | None = None
    currency: str = Field(default="PKR", max_length=10)
    unit: str = Field(default="kg", max_length=20)
    city: str | None = Field(default=None, max_length=100)
    area: str | None = Field(default=None, max_length=100)
    observed_at: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)



class ReportCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    raw_text: str = Field(min_length=1, max_length=4000)


class ReportStatusUpdate(BaseModel):
    status: Literal["accepted", "flagged", "rejected"]


class ReportReviewRequest(BaseModel):
    """Admin review action. Approval makes a suspicious report eligible again."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected"]


class ReportReviewResponse(BaseModel):
    id: UUID
    status: Literal["accepted", "rejected"]
    is_anomalous: bool
    reviewed_at: datetime
    reviewed_by: str


class ReportQueueItem(BaseModel):
    """Review-facing report projection.

    This deliberately omits picker identity, Clerk identifiers, raw picker text,
    and thread information. ``confidence`` is the extraction confidence stored
    with the report, not an anomaly probability; the statistical evidence is in
    ``anomaly_reason`` and ``anomaly_method``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    material: str
    quantity_kg: float
    price_per_kg: float
    currency: str
    unit: Literal["kg"] = "kg"
    city: str | None
    area: str | None
    observed_at: datetime | None
    created_at: datetime
    status: ReportStatus
    is_anomalous: bool
    anomaly_method: str
    anomaly_reason: str
    confidence: float | None = Field(
        default=None,
        description="Extraction confidence recorded with the report, not an anomaly score.",
    )
    reviewed_at: datetime | None = None


class ReportQueueResponse(BaseModel):
    """Paginated reviewer queue. Oldest reports are returned first."""

    items: list[ReportQueueItem]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    pages: int = Field(ge=0)
    has_more: bool


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reporter_id: str
    raw_text: str
    material: str | None
    price_per_kg: Decimal | None
    quantity_kg: Decimal | None
    currency: str
    city: str | None
    area: str | None
    reported_at: datetime | None
    status: str
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReportSubmissionResponse(BaseModel):
    status: Literal["accepted", "needs_clarification", "rejected"]
    report: ReportRead | None = None
    errors: list[str] = Field(default_factory=list)
    clarification_question: str | None = None




class AnomalyVerdict(BaseModel):
    """Outcome of anomaly detection evaluation.

    ``is_anomalous`` is retained for persistence and price eligibility.
    ``outcome`` makes the difference between a clean pass, a suspicious report,
    and a check that could not be completed explicit. A report is never treated
    as fraud by this model; ``suspicious`` means "needs review".
    """

    model_config = ConfigDict(use_enum_values=True)

    is_anomalous: bool
    reason: str
    method: str  # "validation" | "mad" | "ml" | "llm"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    outcome: AnomalyOutcome = "pass"
    sample_size: int = Field(default=0, ge=0)
    median_price_per_kg: Decimal | None = None
    mad_price_per_kg: Decimal | None = None


TIER1_COMPLETED_OUTCOMES: frozenset[str] = frozenset({"pass", "suspicious"})


def tier1_check_completed(verdict: AnomalyVerdict | None) -> bool:
    """Return whether Tier 1 produced a usable conclusion.

    Only ``pass`` and ``suspicious`` mean the deterministic comparison actually
    ran. ``unavailable``, ``insufficient_evidence``, ``error``, ``disabled``, and
    a missing verdict are not conclusions and must never be treated as normal.
    """
    return verdict is not None and verdict.outcome in TIER1_COMPLETED_OUTCOMES


class FinalReport(BaseModel):
    """A validated report guaranteed to have the required sale fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    picker_id: str
    raw_text: str
    material: str
    price_per_kg: Decimal
    quantity_kg: Decimal
    currency: str
    city: str | None
    area: str | None
    observed_at: datetime | None = None
    confidence: float | None
    is_anomalous: bool
    anomaly_reason: str
    anomaly_method: str
    status: Literal["accepted", "flagged", "rejected"]
    reviewed_at: datetime | None = None
    created_at: datetime


class LLMJudgment(BaseModel):
    """Contextual assessment schema.

    The model deliberately has no ability to approve a report: a statistical
    flag is always retained for a human reviewer.
    """

    assessment: Literal["likely_legitimate", "uncertain", "likely_bad_data"] = "uncertain"
    reason: str = Field(max_length=500)
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
