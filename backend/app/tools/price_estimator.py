"""Tool function for price estimation registered with DeepAgents/LangGraph."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.schemas.price import PriceEstimate
from app.services.materials import material_label, normalize_material
from app.services.prices import PriceService

logger = logging.getLogger(__name__)


def _unavailable(
    *,
    material: str,
    location: str | None,
    area: str | None,
    message: str,
) -> dict[str, object]:
    return PriceEstimate(
        material=normalize_material(material) or material,
        material_label=material_label(material),
        location=location,
        area=area,
        currency="PKR",
        estimated_price_per_kg=None,
        source="unavailable",
        geographic_scope="none",
        observation_count=0,
        local_observation_count=0,
        city_observation_count=0,
        evidence_quality="none",
        confidence=0.0,
        message=message,
        limitations=["The price service could not complete this request."],
        generated_at=datetime.now(UTC),
    ).model_dump(mode="json")


async def estimate_price(
    material_str: str,
    location: str = "",
    area: str = "",
) -> dict[str, object]:
    """Estimate scrap price per kg for a material and optional city/area.

    Returns a median estimate from checked picker reports, a clearly labelled
    seed reference, or an explicit unavailable result. It never invents a price.
    """
    city = location.strip() or None
    area_name = area.strip() or None

    try:
        settings = get_settings()
        async with SessionLocal() as session:
            estimate = await PriceService(session=session, settings=settings).estimate(
                material=material_str,
                location=city,
                area=area_name,
            )
    except SQLAlchemyError:
        logger.exception("Price tool could not read report data")
        return _unavailable(
            material=material_str,
            location=city,
            area=area_name,
            message="Price data is temporarily unavailable. Please try again.",
        )

    return estimate.model_dump(mode="json")
