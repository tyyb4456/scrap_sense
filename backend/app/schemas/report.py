"""
Pydantic models and schemas for scrap sale reports, extraction, and anomaly verdicts.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    material: str | None = Field(default=None, max_length=100)
    price_per_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    quantity_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    currency: str = Field(default="PKR", min_length=3, max_length=3)
    city: str | None = Field(default=None, max_length=100)
    area: str | None = Field(default=None, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)



class ReportCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    raw_text: str = Field(min_length=1, max_length=4000)


class ReportStatusUpdate(BaseModel):
    status: Literal["accepted", "flagged", "rejected"]


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
    """Outcome of anomaly detection evaluation."""
    model_config = ConfigDict(use_enum_values=True)

    is_anomalous: bool
    reason: str
    method: str  # "deterministic" | "ml" | "llm"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class LLMJudgment(BaseModel):
    """Schema the LLM judge fills in."""
    is_anomalous: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)