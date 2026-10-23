"""
Pydantic schemas for price estimation requests and responses.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PriceEstimate(BaseModel):
    material_type: str
    location: str
    estimated_price_per_kg: float
    confidence: float = Field(ge=0.0, le=1.0)
    tier_used: str  # "local" | "city" | "seed" | "local+city"
    local_report_count: int
    city_report_count: int


class PriceEstimateRequest(BaseModel):
    material: str
    location: str


class PriceEstimateResponse(PriceEstimate):
    pass