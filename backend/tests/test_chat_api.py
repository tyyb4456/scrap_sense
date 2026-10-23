from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.main_agent import AgentContext
from app.api.routes.chat import get_chat_agent
from app.auth import ClerkUser, require_auth
from app.core.config import Settings, get_settings
from app.main import app

USER = ClerkUser(user_id="user_123", session_id="sess_1", claims={})


class FakeAgent:
    def __init__(self, reply: str = "Try selling plastic in Multan.") -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(
        self,
        payload: dict[str, Any],
        *,
        config: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        self.calls.append({"payload": payload, "config": config, "context": context})
        return {"messages": [AIMessage(content=self.reply)]}


class ExplodingAgent:
    async def ainvoke(
        self,
        _payload: dict[str, Any],
        *,
        config: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        raise RuntimeError("model provider is down")


def post_with_agent(agent: Any, body: dict[str, Any]) -> Any:
    app.dependency_overrides[require_auth] = lambda: USER
    app.dependency_overrides[get_chat_agent] = lambda: agent
    try:
        with TestClient(app) as client:
            return client.post("/api/v1/chat", json=body)
    finally:
        app.dependency_overrides.clear()


def test_chat_returns_the_main_agent_reply() -> None:
    agent = FakeAgent()

    response = post_with_agent(agent, {"message": "plastic ka rate kya hai?"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user_123",
        "reply": "Try selling plastic in Multan.",
    }
    call = agent.calls[0]
    message = call["payload"]["messages"][0]
    assert isinstance(message, HumanMessage)
    assert message.content == "plastic ka rate kya hai?"
    assert call["config"]["configurable"]["thread_id"] == "user_123"
    assert call["context"] == AgentContext(picker_id="user_123")


def test_chat_rejects_empty_message() -> None:
    response = post_with_agent(FakeAgent(), {"message": ""})

    assert response.status_code == 422


def test_chat_requires_authentication() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_secret_key=None, clerk_jwt_key=None
    )
    app.dependency_overrides[get_chat_agent] = lambda: FakeAgent()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat", json={"message": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_chat_returns_503_when_clerk_is_not_configured() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_secret_key=None, clerk_jwt_key=None
    )
    app.dependency_overrides[get_chat_agent] = lambda: FakeAgent()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat",
                json={"message": "hello"},
                headers={"Authorization": "Bearer fake-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_chat_returns_503_when_agent_fails() -> None:
    response = post_with_agent(ExplodingAgent(), {"message": "hello"})

    assert response.status_code == 503
    assert response.json()["detail"] == "ScrapSense agent is unavailable"


def test_chat_returns_502_when_agent_has_no_text() -> None:
    response = post_with_agent(FakeAgent(reply=""), {"message": "hello"})

    assert response.status_code == 502
