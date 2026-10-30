from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agents.main_agent import MainAgentState
from app.agents.report_intaker import scrap_pipeline_agent
from app.schemas.report import AnomalyVerdict, FinalReport, ReportDraft
from app.workflows import pipeline as pipeline_module

ORIGINAL_MESSAGE = "bhai maine aaj do kilo copper becha, 500 rupay per kg, Multan"
COORDINATOR_PARAPHRASE = (
    "Run the scrap report pipeline for a copper sale and return the structured report."
)
PICKER_ID = "user_2clerkSub"


class RecordingExtractionModel:
    def __init__(self, draft: ReportDraft) -> None:
        self.draft = draft
        self.prompts: list[str] = []

    def invoke(self, messages: Any) -> ReportDraft:
        self.prompts.append(messages[0]["content"])
        return self.draft


class ScriptedToolCallingModel(BaseChatModel):
    """Fake coordinator that delegates once, then answers."""

    responses: list[AIMessage]
    index: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-calling"

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=response)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


def valid_draft() -> ReportDraft:
    return ReportDraft(
        material="copper",
        price_per_kg=Decimal("500"),
        quantity_kg=Decimal("2"),
        city="Multan",
    )


def neutral_verdict() -> AnomalyVerdict:
    return AnomalyVerdict(
        is_anomalous=False,
        reason="Price is within the comparable range.",
        method="mad",
        confidence=0.6,
        outcome="pass",
    )


def patch_save_report(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict[str, Any],
) -> None:
    async def fake_save_report(
        *,
        picker_id: str,
        raw_text: str,
        draft: ReportDraft,
        verdict: AnomalyVerdict,
    ) -> FinalReport:
        captured.update(
            picker_id=picker_id,
            raw_text=raw_text,
            draft=draft,
            verdict=verdict,
        )
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
            is_anomalous=verdict.is_anomalous,
            anomaly_reason=verdict.reason,
            anomaly_method=verdict.method,
            status="flagged" if verdict.is_anomalous else "accepted",
            created_at=datetime.now(UTC),
        )

    monkeypatch.setattr(pipeline_module, "save_report", fake_save_report)


def patch_statistical(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_evaluate(_draft: ReportDraft, *, settings: Any) -> AnomalyVerdict:
        return neutral_verdict()

    monkeypatch.setattr(pipeline_module, "evaluate_report_statistical", fake_evaluate)


async def test_coordinator_task_cannot_replace_the_original_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extraction = RecordingExtractionModel(valid_draft())
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: extraction)
    patch_statistical(monkeypatch)
    captured: dict[str, Any] = {}
    patch_save_report(monkeypatch, captured)
    coordinator = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": COORDINATOR_PARAPHRASE,
                            "subagent_type": "scrap_report_pipeline",
                        },
                        "id": "call_1",
                    }
                ],
            ),
            AIMessage(content="done"),
        ]
    )

    agent = cast(
        Any,
        create_deep_agent(
            model=coordinator,
            state_schema=MainAgentState,
            subagents=[scrap_pipeline_agent],
        ),
    )
    await agent.ainvoke(
        {
            "messages": [HumanMessage(content=ORIGINAL_MESSAGE)],
            "original_message": ORIGINAL_MESSAGE,
        },
        {"configurable": {"thread_id": "thread-deepagents", "picker_id": PICKER_ID}},
    )

    assert captured["raw_text"] == ORIGINAL_MESSAGE
    assert captured["picker_id"] == PICKER_ID
    assert ORIGINAL_MESSAGE in extraction.prompts[0]
    assert COORDINATOR_PARAPHRASE not in extraction.prompts[0]


async def test_coordinator_paraphrase_cannot_change_persisted_raw_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extraction = RecordingExtractionModel(valid_draft())
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: extraction)
    patch_statistical(monkeypatch)
    captured: dict[str, Any] = {}
    patch_save_report(monkeypatch, captured)

    result = await pipeline_module.build_pipeline().ainvoke(
        {
            "messages": [HumanMessage(content=COORDINATOR_PARAPHRASE)],
            "original_message": ORIGINAL_MESSAGE,
        },
        {"configurable": {"thread_id": "thread-provenance", "picker_id": PICKER_ID}},
    )

    assert captured["raw_text"] == ORIGINAL_MESSAGE
    assert captured["raw_text"] != COORDINATOR_PARAPHRASE
    assert captured["picker_id"] == PICKER_ID
    assert result["final_report"].raw_text == ORIGINAL_MESSAGE
    assert ORIGINAL_MESSAGE in extraction.prompts[0]
    assert COORDINATOR_PARAPHRASE not in extraction.prompts[0]


def test_extraction_receives_original_message_from_run_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extraction = RecordingExtractionModel(valid_draft())
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: extraction)

    result = pipeline_module.report_draft(
        {"messages": [HumanMessage(content=COORDINATOR_PARAPHRASE)]},
        {"configurable": {"original_message": ORIGINAL_MESSAGE}},
    )

    assert result["report_draft"] == valid_draft()
    assert ORIGINAL_MESSAGE in extraction.prompts[0]
    assert COORDINATOR_PARAPHRASE not in extraction.prompts[0]


async def test_finalize_preserves_original_message_and_clerk_picker_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    patch_save_report(monkeypatch, captured)

    output = await pipeline_module.finalize_report_node(
        {
            "messages": [HumanMessage(content=COORDINATOR_PARAPHRASE)],
            "original_message": ORIGINAL_MESSAGE,
            "report_draft": valid_draft(),
            "deterministic_result": neutral_verdict(),
            "verdict": neutral_verdict(),
        },
        {"configurable": {"thread_id": "thread-1", "picker_id": PICKER_ID}},
    )

    assert captured["picker_id"] == PICKER_ID
    assert captured["raw_text"] == ORIGINAL_MESSAGE
    assert output["final_report"].raw_text == ORIGINAL_MESSAGE


async def test_missing_original_message_is_not_extracted_or_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extraction = RecordingExtractionModel(valid_draft())
    monkeypatch.setattr(pipeline_module, "_extraction_model", lambda: extraction)
    captured: dict[str, Any] = {}
    patch_save_report(monkeypatch, captured)

    result = await pipeline_module.build_pipeline().ainvoke(
        {"messages": [HumanMessage(content=COORDINATOR_PARAPHRASE)]},
        {"configurable": {"thread_id": "thread-no-provenance", "picker_id": PICKER_ID}},
    )

    assert extraction.prompts == []
    assert captured == {}
    assert result.get("final_report") is None
    assert "didn't save" in result["messages"][-1].content.lower()


async def test_finalize_refuses_to_persist_without_original_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    patch_save_report(monkeypatch, captured)

    output = await pipeline_module.finalize_report_node(
        {
            "messages": [HumanMessage(content=COORDINATOR_PARAPHRASE)],
            "report_draft": valid_draft(),
            "deterministic_result": neutral_verdict(),
            "verdict": neutral_verdict(),
        },
        {"configurable": {"thread_id": "thread-1", "picker_id": PICKER_ID}},
    )

    assert captured == {}
    assert "final_report" not in output
    assert "not saved" in output["messages"][0].content.lower()
