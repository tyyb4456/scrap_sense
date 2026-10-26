"""Authenticated price-estimate endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas.price import PriceEstimate
from app.services.prices import PriceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prices", tags=["prices"])


def get_price_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PriceService:
    """Build the price service (overridable in tests)."""
    return PriceService(session=session, settings=settings)


@router.get(
    "/estimate",
    response_model=PriceEstimate,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid Clerk session"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Price data is unavailable"},
    },
)
async def estimate_scrap_price(
    material: Annotated[
        str,
        Query(
            min_length=1,
            max_length=100,
            description="Material name or supported alias, for example plastic.",
        ),
    ],
    user: Annotated[ClerkUser, Depends(require_auth)],
    service: Annotated[PriceService, Depends(get_price_service)],
    location: Annotated[
        str | None,
        Query(
            max_length=100,
            description="City name. Required for report-based evidence.",
        ),
    ] = None,
    area: Annotated[
        str | None,
        Query(
            max_length=100,
            description="Neighbourhood or area within the city, when known.",
        ),
    ] = None,
) -> PriceEstimate:
    """Return a median estimate from eligible reports, seed data, or unavailable.

    The estimate never mixes sources. Local (area) reports are preferred when
    they meet the configured evidence threshold, then city reports, then seed
    prices. A valid request with too little trustworthy evidence returns
    ``source="unavailable"`` and a null price rather than zero or a guess.
    """
    material = material.strip()
    if not material:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="material must not be blank",
        )

    location = location.strip() if location and location.strip() else None
    area = area.strip() if area and area.strip() else None
    if area is not None and location is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="area requires location",
        )

    try:
        return await service.estimate(material=material, location=location, area=area)
    except SQLAlchemyError:
        logger.exception("Price estimation database query failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Price data is unavailable",
        ) from None
