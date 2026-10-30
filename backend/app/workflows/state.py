"""
State schema for the report intake and anomaly pipeline workflow.
"""

from __future__ import annotations

from typing import NotRequired

from langgraph.graph import MessagesState

from app.schemas.report import AnomalyVerdict, FinalReport, ReportDraft
from app.services.report_validation import ValidationResult


class PipelineState(MessagesState):
    original_message: NotRequired[str | None]
    report_draft: NotRequired[ReportDraft | None]
    validation_result: NotRequired[ValidationResult | None]
    deterministic_result: NotRequired[AnomalyVerdict | None]
    ml_result: NotRequired[AnomalyVerdict | None]
    llm_result: NotRequired[AnomalyVerdict | None]
    verdict: NotRequired[AnomalyVerdict | None]
    final_report: NotRequired[FinalReport | None]
    structured_response: NotRequired[FinalReport | None]
