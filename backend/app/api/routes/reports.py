"""Reviewer-only report queue and human review decisions.

Only Clerk users listed in ``ADMIN_USER_IDS`` can read the queue or approve and
reject reports. Approval is the only path that returns a suspicious report to
price eligibility.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_admin
from app.db.session import get_session
from app.schemas.report import (
    ReportQueueItem,
    ReportQueueResponse,
    ReportReviewRequest,
    ReportReviewResponse,
    ReportStatus,
)
from app.services.reports import (
    ReportReviewConflict,
    get_report_for_review,
    list_reports_for_review,
    review_report,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "",
    response_model=ReportQueueResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid Clerk session"},
        status.HTTP_403_FORBIDDEN: {"description": "Reviewer access required"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Report store unavailable"},
    },
)
async def list_reports(
    reviewer: Annotated[ClerkUser, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    report_status: Annotated[
        ReportStatus,
        Query(alias="status", description="Report status to list. Defaults to flagged."),
    ] = "flagged",
    page: Annotated[int, Query(ge=1, description="One-based page number.")] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Reports per page (maximum 100)."),
    ] = 20,
) -> ReportQueueResponse:
    """Return a deterministic page of reports awaiting reviewer attention."""
    try:
        reports, total = await list_reports_for_review(
            session,
            status=report_status,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
    except SQLAlchemyError:
        logger.exception("Report queue database query failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report queue is unavailable",
        ) from None

    pages = (total + page_size - 1) // page_size
    return ReportQueueResponse(
        items=[ReportQueueItem.model_validate(report) for report in reports],
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
        has_more=page * page_size < total,
    )


@router.get(
    "/{report_id}",
    response_model=ReportQueueItem,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid Clerk session"},
        status.HTTP_403_FORBIDDEN: {"description": "Reviewer access required"},
        status.HTTP_404_NOT_FOUND: {"description": "Report not found"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Report store unavailable"},
    },
)
async def get_report(
    report_id: UUID,
    reviewer: Annotated[ClerkUser, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReportQueueItem:
    """Return the review projection for a single report."""
    try:
        report = await get_report_for_review(session, report_id=report_id)
    except SQLAlchemyError:
        logger.exception("Report detail database query failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report review is unavailable",
        ) from None

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    return ReportQueueItem.model_validate(report)


@router.patch(
    "/{report_id}/review",
    response_model=ReportReviewResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid Clerk session"},
        status.HTTP_403_FORBIDDEN: {"description": "Reviewer access required"},
        status.HTTP_404_NOT_FOUND: {"description": "Report not found"},
        status.HTTP_409_CONFLICT: {"description": "Report is not awaiting review"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Report store unavailable"},
    },
)
async def review(
    report_id: UUID,
    body: ReportReviewRequest,
    reviewer: Annotated[ClerkUser, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReportReviewResponse:
    """Approve or reject a flagged report. Already-decided reports conflict."""
    try:
        report = await review_report(
            session,
            report_id=report_id,
            reviewer_id=reviewer.user_id,
            status=body.status,
        )
    except ReportReviewConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Report is already {exc.current_status} and cannot be reviewed again",
        ) from None
    except SQLAlchemyError:
        await session.rollback()
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
