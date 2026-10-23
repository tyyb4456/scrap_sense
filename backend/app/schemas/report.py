from decimal import Decimal

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
