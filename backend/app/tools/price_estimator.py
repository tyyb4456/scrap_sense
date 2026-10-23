"""
Tool function for price estimation registered with DeepAgents/LangGraph.
"""

from __future__ import annotations

from app.schemas.price import PriceEstimate


def estimate_price(material_str: str, location: str) -> dict[str, object]:
    """
    Estimate scrap price per kg for a given material type in a specific location or neighborhood.
    Returns estimated price per kg, confidence score, and regional sample statistics.
    """
    return PriceEstimate(
        material_type=material_str,
        location=location,
        estimated_price_per_kg=0.0,
        confidence=0.0,
        tier_used="seed",
        local_report_count=0,
        city_report_count=0,
    ).model_dump()