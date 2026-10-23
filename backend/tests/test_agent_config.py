import pytest
from deepagents import HarnessProfile
from pydantic import ValidationError

from app.agents import deep_agent
from app.core.config import Settings
from app.schemas.report import ReportDraft


def test_ai_model_requires_provider_prefix() -> None:
    with pytest.raises(ValidationError):
        Settings(ai_model="gpt-4.1-mini")


def test_agent_is_built_without_default_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    registered_key: str | None = None
    registered_profile: HarnessProfile | None = None
    sentinel = object()

    def fake_create_deep_agent(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    def fake_register_profile(key: str, profile: HarnessProfile) -> None:
        nonlocal registered_key, registered_profile
        registered_key = key
        registered_profile = profile

    monkeypatch.setattr(deep_agent, "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(deep_agent, "register_harness_profile", fake_register_profile)

    agent = deep_agent.build_report_intake_agent(Settings(ai_model="openai:test-model"))

    assert agent is sentinel
    assert registered_key == "openai:test-model"
    assert registered_profile is not None
    assert registered_profile.excluded_tools == deep_agent.DISABLED_TOOLS
    assert registered_profile.general_purpose_subagent is not None
    assert registered_profile.general_purpose_subagent.enabled is False
    assert captured["model"] == "openai:test-model"
    assert captured["tools"] == []
    assert captured["response_format"] is ReportDraft
    assert captured["name"] == "report_intake"


async def test_extractor_reads_structured_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAgent:
        async def ainvoke(self, payload: dict[str, object]) -> dict[str, object]:
            assert payload["messages"]
            return {
                "structured_response": {
                    "material": "copper",
                    "price_per_kg": "500",
                    "quantity_kg": "2",
                }
            }

    monkeypatch.setattr(deep_agent, "create_deep_agent", lambda **_: FakeAgent())
    monkeypatch.setattr(deep_agent, "register_harness_profile", lambda *_: None)

    extractor = deep_agent.build_deep_agent_extractor(Settings(ai_model="openai:test-model"))
    draft = await extractor("sold 2 kg copper at 500 per kg")

    assert draft.material == "copper"
    assert str(draft.price_per_kg) == "500"
