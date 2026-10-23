from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.schemas.report import LLMJudgment, ReportDraft
from app.workflows import pipeline as pipeline_module


class FakeModel:
    def __init__(self, value: Any) -> None:
        self.value = value

    def invoke(self, _messages: Any) -> Any:
        return self.value


class ExplodingModel:
    def invoke(self, _messages: Any) -> Any:
        raise RuntimeError("provider secret")


def valid_draft() -> ReportDraft:
    return ReportDraft(
        material="copper",
        price_per_kg=Decimal("500"),
        quantity_kg=Decimal("2"),
        city="Multan",
    )


def test_report_draft_extracts_structured_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = valid_draft()
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(draft))

    result = pipeline_module.report_draft(
        {"messages": [HumanMessage(content="sold 2kg copper at 500 per kg")]}
    )

    assert result["report_draft"] == draft


def test_extraction_failure_falls_back_to_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: ExplodingModel())

    result = pipeline_module.report_draft(
        {"messages": [HumanMessage(content="sold 2kg copper")]}
    )

    draft = result["report_draft"]
    assert draft.needs_clarification is True
    assert draft.clarification_question
    assert "provider secret" not in draft.clarification_question


def test_validate_and_build_asks_for_missing_fields() -> None:
    result = pipeline_module.validate_and_build(
        {"messages": [], "report_draft": ReportDraft(material="copper")}
    )

    message = result["messages"][0]
    assert isinstance(message, AIMessage)
    assert "price per kg" in message.content
    assert "quantity in kg" in message.content


def test_route_after_validation_stops_on_clarification() -> None:
    assert (
        pipeline_module.route_after_validation(
            {"messages": [], "report_draft": ReportDraft(material="copper")}
        )
        == "end"
    )
    assert (
        pipeline_module.route_after_validation(
            {"messages": [], "report_draft": valid_draft()}
        )
        == "deterministic_check"
    )


def test_deterministic_and_ml_checks_are_neutral() -> None:
    deterministic = pipeline_module.deterministic_check_node({"messages": []})[
        "deterministic_result"
    ]
    ml = pipeline_module.ml_check_node({"messages": []})["ml_result"]

    assert deterministic.method == "deterministic"
    assert deterministic.is_anomalous is False
    assert ml.method == "ml"
    assert ml.is_anomalous is False


def test_llm_check_uses_judgment(monkeypatch: pytest.MonkeyPatch) -> None:
    judgment = LLMJudgment(
        is_anomalous=True,
        reason="Price is far above the local range.",
        confidence=0.8,
    )
    monkeypatch.setattr(pipeline_module, "_judge_model", lambda: FakeModel(judgment))

    result = pipeline_module.llm_check_node(
        {"messages": [], "report_draft": valid_draft()}
    )

    verdict = result["verdict"]
    assert verdict.is_anomalous is True
    assert verdict.method == "llm"
    assert verdict.confidence == 0.8


def test_accept_reports_a_flagged_verdict() -> None:
    verdict = pipeline_module.AnomalyVerdict(
        is_anomalous=True,
        reason="Quantity looks wrong.",
        method="ml",
        confidence=0.9,
    )

    result = pipeline_module.accept_node(
        {"messages": [], "report_draft": valid_draft(), "verdict": verdict}
    )

    assert result["verdict"] == verdict
    assert "flagged" in result["messages"][0].content.lower()


async def test_pipeline_accepts_a_valid_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(valid_draft()))
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="sold 2kg copper at 500 per kg")]}
    )

    assert result["report_draft"].material == "copper"
    assert result["verdict"].is_anomalous is False
    assert "accepted" in result["messages"][-1].content.lower()


async def test_pipeline_asks_for_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incomplete = ReportDraft(material="copper", quantity_kg=Decimal("2"))
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(incomplete))
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="sold 2kg copper")]}
    )

    assert "verdict" not in result
    assert "price per kg" in result["messages"][-1].content
