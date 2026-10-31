from __future__ import annotations

from typing import Any, cast

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from app.agents import main_agent
from app.agents.report_intaker import scrap_pipeline_agent
from app.core.config import Settings
from app.workflows.pipeline import pipeline


def test_intake_subagent_wraps_the_pipeline() -> None:
    assert scrap_pipeline_agent["name"] == "scrap_report_pipeline"
    assert scrap_pipeline_agent["runnable"] is pipeline


def test_build_agent_wires_postgres_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()
    store = cast(BaseStore, object())
    checkpointer = cast(BaseCheckpointSaver, object())

    def fake_create_deep_agent(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(main_agent, "create_deep_agent", fake_create_deep_agent)

    agent = main_agent.build_agent(
        settings=Settings(xkiro_model="test-model"),
        store=store,
        checkpointer=checkpointer,
    )

    assert agent is sentinel
    assert captured["subagents"] == [scrap_pipeline_agent]
    assert captured["tools"] == [main_agent.estimate_price]
    assert captured["context_schema"] is main_agent.AgentContext
    assert captured["state_schema"] is main_agent.MainAgentState
    assert captured["checkpointer"] is checkpointer
    assert captured["store"] is store
    assert captured["backend"] is not None
    assert captured["memory"] == [main_agent.MEMORY_FILE_PATH]


def test_agent_context_carries_picker_id() -> None:
    context = main_agent.AgentContext(picker_id="user_123")

    assert context.picker_id == "user_123"


def test_coordinator_state_declares_the_original_message() -> None:
    assert "original_message" in main_agent.MainAgentState.__annotations__
