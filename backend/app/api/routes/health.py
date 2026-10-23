import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


@router.get("/live", response_model=LivenessResponse)
async def liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LivenessResponse:
    return LivenessResponse(status="ok", version=settings.app_version)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessResponse:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database readiness check failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="degraded",
            database="unavailable",
            version=settings.app_version,
        )

    return ReadinessResponse(
        status="ok",
        database="ok",
        version=settings.app_version,
    )
