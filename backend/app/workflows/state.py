"""
State schema for the report intake and anomaly pipeline workflow.
"""

from __future__ import annotations

from typing import NotRequired

from langgraph.graph import MessagesState

from app.schemas.report import AnomalyVerdict, ReportDraft


class PipelineState(MessagesState):
    report_draft: NotRequired[ReportDraft | None]
    deterministic_result: NotRequired[AnomalyVerdict | None]
    ml_result: NotRequired[AnomalyVerdict | None]
    verdict: NotRequired[AnomalyVerdict | None]
