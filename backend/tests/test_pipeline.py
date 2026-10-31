from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.schemas.report import AnomalyVerdict, FinalReport, LLMJudgment, ReportDraft
from app.workflows import pipeline as pipeline_module
from app.workflows.state import PipelineState


class FakeModel:
    def __init__(self, value: Any) -> None:
        self.value = value

    def invoke(self, _messages: Any) -> Any:
        return self.value


class AsyncFakeModel:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def ainvoke(self, _messages: Any) -> Any:
        return self.value


class ExplodingModel:
    def invoke(self, _messages: Any) -> Any:
        raise RuntimeError("provider secret")


class ExplodingAsyncModel:
    async def ainvoke(self, _messages: Any) -> Any:
        raise RuntimeError("provider secret")


class SlowAsyncModel:
    async def ainvoke(self, _messages: Any) -> Any:
        await asyncio.sleep(1)
        return LLMJudgment(assessment="likely_bad_data", reason="too late", confidence=0.9)


class RecordingAsyncModel:
    def __init__(self, value: Any) -> None:
        self.value = value
        self.calls = 0

    async def ainvoke(self, _messages: Any) -> Any:
        self.calls += 1
        return self.value


def valid_draft() -> ReportDraft:
    return ReportDraft(
        material="copper",
        price_per_kg=Decimal("500"),
        quantity_kg=Decimal("2"),
        city="Multan",
    )


def verdict(
    *,
    is_anomalous: bool = False,
    outcome: str = "pass",
    reason: str = "Price is within the comparable range.",
    method: str = "mad",
    confidence: float = 0.6,
) -> AnomalyVerdict:
    return AnomalyVerdict(
        is_anomalous=is_anomalous,
        reason=reason,
        method=method,
        confidence=confidence,
        outcome=outcome,  # type: ignore[arg-type]
    )


def final_report(
    draft: ReportDraft,
    result: AnomalyVerdict,
    *,
    picker_id: str = "user_123",
    raw_text: str = "sold 2kg copper at 500 per kg",
) -> FinalReport:
    return FinalReport(
        id=uuid4(),
        picker_id=picker_id,
        raw_text=raw_text,
        material=draft.material or "",
        price_per_kg=draft.price_per_kg or Decimal("0"),
        quantity_kg=draft.quantity_kg or Decimal("0"),
        currency=draft.currency,
        city=draft.city,
        area=draft.area,
        observed_at=draft.observed_at,
        confidence=draft.confidence,
        is_anomalous=result.is_anomalous,
        anomaly_reason=result.reason,
        anomaly_method=result.method,
        anomaly_outcome=result.outcome,
        status=(
            "pending_evidence"
            if result.outcome == "insufficient_evidence"
            else "flagged"
            if result.is_anomalous
            else "accepted"
        ),
        created_at=datetime.now(UTC),
    )


def patch_save_report(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict[str, Any] | None = None,
) -> None:
    async def fake_save_report(
        *,
        picker_id: str,
        raw_text: str,
        draft: ReportDraft,
        verdict: AnomalyVerdict,
    ) -> FinalReport:
        if captured is not None:
            captured.update(
                picker_id=picker_id,
                raw_text=raw_text,
                draft=draft,
                verdict=verdict,
            )
        return final_report(draft, verdict, picker_id=picker_id, raw_text=raw_text)

    monkeypatch.setattr(pipeline_module, "save_report", fake_save_report)


def patch_statistical(
    monkeypatch: pytest.MonkeyPatch,
    result: AnomalyVerdict,
    *,
    calls: list[str] | None = None,
) -> None:
    async def fake_evaluate(_draft: ReportDraft, *, settings: Any) -> AnomalyVerdict:
        if calls is not None:
            calls.append("deterministic")
        return result

    monkeypatch.setattr(pipeline_module, "evaluate_report_statistical", fake_evaluate)


def test_report_draft_extracts_structured_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = valid_draft()
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(draft))
    stale = verdict(
        is_anomalous=True,
        outcome="suspicious",
        reason="Stale flag from an earlier turn.",
    )

    result = pipeline_module.report_draft(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
            "validation_result": None,
            "deterministic_result": stale,
            "ml_result": stale,
            "llm_result": stale,
            "verdict": stale,
            "final_report": final_report(draft, stale),
            "structured_response": final_report(draft, stale),
        }
    )

    assert result["report_draft"] == draft
    assert result["deterministic_result"] is None
    assert result["ml_result"] is None
    assert result["llm_result"] is None
    assert result["verdict"] is None
    assert result["final_report"] is None
    assert result["structured_response"] is None


def test_extraction_failure_falls_back_to_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: ExplodingModel())

    result = pipeline_module.report_draft(
        {
            "messages": [HumanMessage(content="sold 2kg copper")],
            "original_message": "sold 2kg copper",
        }
    )

    draft = result["report_draft"]
    assert draft.needs_clarification is True
    assert draft.clarification_question
    assert "provider secret" not in draft.clarification_question


def test_validate_and_build_asks_for_missing_fields() -> None:
    draft = ReportDraft(material="copper")
    result = pipeline_module.validate_and_build(
        {"messages": [], "report_draft": draft}
    )

    message = result["messages"][0]
    assert isinstance(message, AIMessage)
    assert "price per kg" in message.content
    assert "quantity in kg" in message.content
    assert result["validation_result"].is_valid is False
    assert "missing_price" in result["validation_result"].codes
    assert "missing_quantity" in result["validation_result"].codes


def test_validate_and_build_rejects_unsupported_currency() -> None:
    draft = valid_draft().model_copy(
        update={
            "currency": "USD",
            "clarification_question": "Could you clarify the sale details?",
        }
    )
    result = pipeline_module.validate_and_build(
        {"messages": [], "report_draft": draft}
    )

    assert result["validation_result"].is_valid is False
    assert "unsupported_currency" in result["validation_result"].codes
    assert "currency" in result["messages"][0].content


def test_route_after_validation_stops_on_clarification() -> None:
    invalid = pipeline_module.validate_and_build(
        {"messages": [], "report_draft": ReportDraft(material="copper")}
    )
    valid = pipeline_module.validate_and_build(
        {"messages": [], "report_draft": valid_draft()}
    )

    invalid_state = {
        "messages": [],
        "report_draft": ReportDraft(material="copper"),
        "validation_result": invalid["validation_result"],
    }
    valid_state = {
        "messages": [],
        "report_draft": valid_draft(),
        "validation_result": valid["validation_result"],
    }

    assert (
        pipeline_module.route_after_validation(cast(PipelineState, invalid_state)) == "end"
    )
    assert (
        pipeline_module.route_after_validation(cast(PipelineState, valid_state))
        == "deterministic_check"
    )


async def test_deterministic_node_returns_the_statistical_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = verdict(reason="Price is within the comparable range.")
    patch_statistical(monkeypatch, expected)

    result = await pipeline_module.deterministic_check_node(
        {"messages": [], "report_draft": valid_draft()}
    )

    assert result["deterministic_result"] == expected


def test_ml_check_is_explicitly_disabled() -> None:
    result = pipeline_module.ml_check_node({"messages": []})["ml_result"]

    assert result.method == "ml"
    assert result.is_anomalous is False
    assert result.outcome == "disabled"


async def test_llm_check_uses_judgment_but_retains_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    judgment = LLMJudgment(
        assessment="likely_legitimate",
        reason="High-grade copper can legitimately sell above the median.",
        confidence=0.8,
    )
    monkeypatch.setattr(pipeline_module, "_judge_model", lambda: AsyncFakeModel(judgment))
    statistical = verdict(
        is_anomalous=True,
        outcome="suspicious",
        reason="Price is a statistical outlier.",
        confidence=0.7,
    )

    result = await pipeline_module.llm_check_node(
        {
            "messages": [],
            "report_draft": valid_draft(),
            "deterministic_result": statistical,
        }
    )

    llm_result = result["llm_result"]
    assert llm_result.is_anomalous is True
    assert llm_result.method == "llm"
    assert llm_result.confidence == 0.8
    assert "likely_legitimate" in llm_result.reason
    assert "Statistical flag retained" in llm_result.reason


async def test_llm_failure_does_not_clear_a_statistical_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_module, "_judge_model", lambda: ExplodingAsyncModel()
    )
    statistical = verdict(
        is_anomalous=True,
        outcome="suspicious",
        reason="Price is a statistical outlier.",
    )

    result = await pipeline_module.llm_check_node(
        {
            "messages": [],
            "report_draft": valid_draft(),
            "deterministic_result": statistical,
        }
    )

    assert result["llm_result"].is_anomalous is True
    assert "unavailable" in result["llm_result"].reason.lower()


async def test_llm_timeout_does_not_clear_a_statistical_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_judge_model", lambda: SlowAsyncModel())
    monkeypatch.setattr(pipeline_module.settings, "anomaly_llm_timeout_seconds", 0.01)
    statistical = verdict(
        is_anomalous=True,
        outcome="suspicious",
        reason="Price is a statistical outlier.",
    )

    result = await pipeline_module.llm_check_node(
        {
            "messages": [],
            "report_draft": valid_draft(),
            "deterministic_result": statistical,
        }
    )

    assert result["llm_result"].is_anomalous is True
    assert "timed out" in result["llm_result"].reason.lower()


async def test_llm_malformed_output_does_not_clear_a_statistical_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_module, "_judge_model", lambda: AsyncFakeModel(object())
    )
    statistical = verdict(
        is_anomalous=True,
        outcome="suspicious",
        reason="Price is a statistical outlier.",
    )

    result = await pipeline_module.llm_check_node(
        {
            "messages": [],
            "report_draft": valid_draft(),
            "deterministic_result": statistical,
        }
    )

    assert result["llm_result"].is_anomalous is True
    assert "unavailable" in result["llm_result"].reason.lower()


def test_accept_reports_a_flagged_verdict() -> None:
    flagged = verdict(
        is_anomalous=True,
        outcome="suspicious",
        reason="Quantity looks wrong.",
        method="ml",
        confidence=0.9,
    )

    result = pipeline_module.accept_node(
        {
            "messages": [],
            "report_draft": valid_draft(),
            "deterministic_result": flagged,
            "verdict": flagged,
        }
    )

    assert result["verdict"] == flagged
    assert "flagged" in result["messages"][0].content.lower()
    assert "not affect prices" in result["messages"][0].content.lower()


async def test_pipeline_accepts_a_valid_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(valid_draft()))
    patch_statistical(monkeypatch, verdict())
    patch_save_report(monkeypatch)
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert result["report_draft"].material == "copper"
    assert result["verdict"].is_anomalous is False
    assert result["deterministic_result"].outcome == "pass"
    assert result["ml_result"].outcome == "disabled"
    assert "saved" in result["messages"][-1].content.lower()
    assert result["structured_response"].picker_id == "user_123"


async def test_invalid_report_never_reaches_anomaly_or_llm_tiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = ReportDraft(
        material="copper",
        price_per_kg=Decimal("-5"),
        quantity_kg=Decimal("2"),
        city="Multan",
    )
    calls: list[str] = []
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(invalid))
    patch_statistical(monkeypatch, verdict(), calls=calls)
    monkeypatch.setattr(
        pipeline_module,
        "_judge_model",
        lambda: ExplodingAsyncModel(),
    )
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper for minus 5")],
            "original_message": "sold 2kg copper for minus 5",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert calls == []
    assert result.get("deterministic_result") is None
    assert result.get("ml_result") is None
    assert result.get("llm_result") is None
    assert result.get("final_report") is None
    assert "price per kg" in result["messages"][-1].content


async def test_ml_tier_is_reached_for_every_valid_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(valid_draft()))
    patch_statistical(monkeypatch, verdict(), calls=calls)

    def fake_ml_check(_settings: Any) -> AnomalyVerdict:
        calls.append("ml")
        return verdict(method="ml", outcome="disabled")

    monkeypatch.setattr(pipeline_module, "evaluate_ml_check", fake_ml_check)
    graph = pipeline_module.build_pipeline()

    await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert calls == ["deterministic", "ml"]


async def test_llm_tier_is_reachable_when_enabled_and_suspicious(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(valid_draft()))
    patch_statistical(
        monkeypatch,
        verdict(
            is_anomalous=True,
            outcome="suspicious",
            reason="Price is a statistical outlier.",
        ),
    )
    monkeypatch.setattr(pipeline_module.settings, "use_llm_reasoning", True)
    monkeypatch.setattr(
        pipeline_module,
        "_judge_model",
        lambda: AsyncFakeModel(
            LLMJudgment(
                assessment="likely_bad_data",
                reason="The value is implausible for this context.",
                confidence=0.9,
            )
        ),
    )
    patch_save_report(monkeypatch)
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert result["llm_result"].method == "llm"
    assert result["verdict"].is_anomalous is True
    assert result["structured_response"].status == "flagged"


async def test_llm_tier_is_skipped_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(valid_draft()))
    patch_statistical(
        monkeypatch,
        verdict(
            is_anomalous=True,
            outcome="suspicious",
            reason="Price is a statistical outlier.",
        ),
    )
    monkeypatch.setattr(pipeline_module.settings, "use_llm_reasoning", False)
    monkeypatch.setattr(pipeline_module, "_judge_model", lambda: ExplodingAsyncModel())
    patch_save_report(monkeypatch)
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert result.get("llm_result") is None
    assert result["verdict"].is_anomalous is True
    assert result["structured_response"].status == "flagged"


async def test_insufficient_evidence_is_persisted_as_pending_without_ml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(valid_draft()))
    patch_statistical(
        monkeypatch,
        verdict(
            outcome="insufficient_evidence",
            reason="Not enough comparable historical reports (1 < 5).",
            confidence=0.0,
        ),
    )
    patch_save_report(monkeypatch, captured)
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert captured["verdict"].outcome == "insufficient_evidence"
    assert result["structured_response"].status == "pending_evidence"
    assert result["structured_response"].is_anomalous is False
    assert result["verdict"].outcome == "insufficient_evidence"
    assert result.get("ml_result") is None
    assert "pending evidence" in result["messages"][-1].content.lower()
    assert "accepted" not in result["messages"][-1].content.lower()


async def test_unavailable_tier1_stops_before_ml_and_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(valid_draft()))
    patch_statistical(
        monkeypatch,
        verdict(
            outcome="unavailable",
            reason="Historical comparison was unavailable.",
            confidence=0.0,
        ),
    )
    patch_save_report(monkeypatch, captured)
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert captured == {}
    assert result.get("final_report") is None
    assert result.get("structured_response") is None
    assert result.get("ml_result") is None
    assert result["verdict"].outcome == "unavailable"
    assert result["verdict"].is_anomalous is False
    assert "not saved" in result["messages"][-1].content.lower()
    assert "accepted" not in result["messages"][-1].content.lower()


async def test_unexpected_deterministic_exception_fails_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def explode(_draft: ReportDraft, *, settings: Any) -> AnomalyVerdict:
        raise RuntimeError("database connection reset")

    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(valid_draft()))
    monkeypatch.setattr(pipeline_module, "evaluate_report_statistical", explode)
    patch_save_report(monkeypatch, captured)
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert result["deterministic_result"].outcome == "unavailable"
    assert captured == {}
    assert result.get("final_report") is None
    assert result.get("structured_response") is None
    assert "not saved" in result["messages"][-1].content.lower()


async def test_tier3_cannot_override_unavailable_tier1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    judge = RecordingAsyncModel(
        LLMJudgment(
            assessment="likely_legitimate",
            reason="This sale looks fine.",
            confidence=0.9,
        )
    )
    monkeypatch.setattr(pipeline_module, "_judge_model", lambda: judge)

    result = await pipeline_module.llm_check_node(
        {
            "messages": [],
            "report_draft": valid_draft(),
            "deterministic_result": verdict(
                outcome="unavailable",
                reason="Historical comparison was unavailable.",
                confidence=0.0,
            ),
        }
    )

    assert judge.calls == 0
    assert result["llm_result"].outcome == "unavailable"
    assert result["llm_result"].is_anomalous is False


def test_tier2_cannot_turn_unavailable_into_normal() -> None:
    unavailable = verdict(
        outcome="unavailable",
        reason="Historical comparison was unavailable.",
        confidence=0.0,
    )
    ml_pass = verdict(outcome="pass", method="ml")
    state = cast(
        PipelineState,
        {
            "messages": [],
            "deterministic_result": unavailable,
            "ml_result": ml_pass,
        },
    )

    resolved = pipeline_module._resolve_verdict(state)
    assert resolved.outcome == "unavailable"
    assert resolved.is_anomalous is False
    assert pipeline_module.route_after_deterministic(state) == "processing_unavailable"


def test_missing_tier1_outcome_does_not_default_to_normal() -> None:
    state = cast(
        PipelineState,
        {"messages": [], "ml_result": verdict(outcome="pass", method="ml")},
    )

    resolved = pipeline_module._resolve_verdict(state)
    assert resolved.outcome == "unavailable"
    assert resolved.is_anomalous is False
    assert pipeline_module.route_after_deterministic(state) == "processing_unavailable"


def test_accept_node_does_not_accept_unavailable() -> None:
    unavailable = verdict(
        outcome="unavailable",
        reason="Historical comparison was unavailable.",
        confidence=0.0,
    )

    result = pipeline_module.accept_node(
        cast(
            PipelineState,
            {
                "messages": [],
                "report_draft": valid_draft(),
                "deterministic_result": unavailable,
            },
        )
    )

    assert "not saved" in result["messages"][0].content.lower()
    assert "accepted" not in result["messages"][0].content.lower()


async def test_finalize_refuses_unavailable_even_when_called_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    patch_save_report(monkeypatch, captured)
    unavailable = verdict(
        outcome="unavailable",
        reason="Historical comparison was unavailable.",
        confidence=0.0,
    )

    output = await pipeline_module.finalize_report_node(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
            "report_draft": valid_draft(),
            "deterministic_result": unavailable,
            "verdict": unavailable,
        },
        {"configurable": {"thread_id": "picker-42"}},
    )

    assert captured == {}
    assert "final_report" not in output
    assert "not saved" in output["messages"][0].content.lower()


async def test_finalize_report_persists_the_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    patch_save_report(monkeypatch, captured)
    draft = valid_draft()
    result = verdict(reason="Price is within range.")

    output = await pipeline_module.finalize_report_node(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
            "report_draft": draft,
            "deterministic_result": result,
            "verdict": result,
        },
        {"configurable": {"thread_id": "picker-42"}},
    )

    assert captured["picker_id"] == "picker-42"
    assert captured["draft"] == draft
    assert captured["verdict"] == result
    assert output["final_report"].material == "copper"
    assert output["structured_response"] == output["final_report"]
    assert "saved" in output["messages"][0].content.lower()


async def test_finalize_report_prefers_authenticated_picker_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    patch_save_report(monkeypatch, captured)

    await pipeline_module.finalize_report_node(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg")],
            "original_message": "sold 2kg copper at 500 per kg",
            "report_draft": valid_draft(),
            "deterministic_result": verdict(reason="Price is within range."),
            "verdict": verdict(reason="Price is within range."),
        },
        {"configurable": {"thread_id": "thread-1", "picker_id": "user_123"}},
    )

    assert captured["picker_id"] == "user_123"


async def test_finalize_report_skips_an_incomplete_draft() -> None:
    output = await pipeline_module.finalize_report_node(
        {
            "messages": [HumanMessage(content="sold copper")],
            "report_draft": ReportDraft(material="copper"),
        },
        {"configurable": {"thread_id": "picker-42"}},
    )

    assert "final_report" not in output
    assert "could not build" in output["messages"][0].content.lower()


async def test_pipeline_asks_for_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incomplete = ReportDraft(material="copper", quantity_kg=Decimal("2"))
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(incomplete))
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper")],
            "original_message": "sold 2kg copper",
        }
    )

    assert result.get("verdict") is None
    assert result.get("final_report") is None
    assert "price per kg" in result["messages"][-1].content


async def test_missing_city_asks_for_clarification_without_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cityless = ReportDraft(
        material="copper",
        price_per_kg=Decimal("500"),
        quantity_kg=Decimal("2"),
        area="Shah Rizwan",
    )
    captured: dict[str, Any] = {}
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(cityless))
    patch_save_report(monkeypatch, captured)
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg in Shah Rizwan")],
            "original_message": "sold 2kg copper at 500 per kg in Shah Rizwan",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert captured == {}
    assert result.get("final_report") is None
    assert result.get("deterministic_result") is None
    assert "missing_city" in result["validation_result"].codes
    assert "city" in result["messages"][-1].content.lower()


async def test_ambiguous_city_extraction_asks_for_clarification_without_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ambiguous = ReportDraft(
        material="copper",
        price_per_kg=Decimal("500"),
        quantity_kg=Decimal("2"),
        city="not sure",
        needs_clarification=True,
        clarification_question="Which city was the sale in?",
    )
    captured: dict[str, Any] = {}
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: FakeModel(ambiguous))
    patch_save_report(monkeypatch, captured)
    graph = pipeline_module.build_pipeline()

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="sold 2kg copper at 500 per kg somewhere")],
            "original_message": "sold 2kg copper at 500 per kg somewhere",
        },
        {"configurable": {"thread_id": "user_123"}},
    )

    assert captured == {}
    assert result.get("final_report") is None
    assert "missing_city" in result["validation_result"].codes
    assert result["messages"][-1].content == "Which city was the sale in?"
