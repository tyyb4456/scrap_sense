from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.report import ReportDraft

IntakeStatus = Literal["accepted", "needs_clarification", "rejected"]


class ReportIntakeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reporter_id: str = Field(min_length=1, max_length=128)
    raw_text: str = Field(min_length=1, max_length=4000)


class ReportIntakeResult(BaseModel):
    status: IntakeStatus
    draft: ReportDraft | None = None
    errors: list[str] = Field(default_factory=list)
    clarification_question: str | None = None


class ReportIntakeState(TypedDict, total=False):
    reporter_id: str
    raw_text: str
    draft: ReportDraft | None
    errors: list[str]
    status: IntakeStatus
    clarification_question: str | None
