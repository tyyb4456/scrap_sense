"""Admin report-review endpoint.

Only reviewers listed in ``ADMIN_USER_IDS`` can approve or reject a report.
Approval is the only path that returns a suspicious report to price eligibility.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_admin
from app.db.session import get_session
from app.schemas.report import ReportReviewRequest, ReportReviewResponse
from app.services.reports import review_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.patch(
    "/{report_id}/review",
    response_model=ReportReviewResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid Clerk session"},
        status.HTTP_403_FORBIDDEN: {"description": "Reviewer access required"},
        status.HTTP_404_NOT_FOUND: {"description": "Report not found"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Report store unavailable"},
    },
)
async def review(
    report_id: UUID,
    body: ReportReviewRequest,
    reviewer: Annotated[ClerkUser, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReportReviewResponse:
    try:
        report = await review_report(
            session,
            report_id=report_id,
            reviewer_id=reviewer.user_id,
            status=body.status,
        )
    except SQLAlchemyError:
        logger.exception("Report review database operation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report review is unavailable",
        ) from None

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    if report.reviewed_at is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report review could not be recorded",
        )

    return ReportReviewResponse(
        id=report.id,
        status=body.status,
        is_anomalous=report.is_anomalous,
        reviewed_at=report.reviewed_at,
        reviewed_by=reviewer.user_id,
    )
