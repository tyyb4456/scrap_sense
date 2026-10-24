from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.main_agent import AgentContext
from app.api.routes.chat import get_chat_agent, get_checkpointer
from app.auth import ClerkUser, require_auth
from app.core.config import Settings, get_settings
from app.main import app
from app.models.chat_thread import DEFAULT_THREAD_TITLE, ChatThread
from app.services.chat_threads import get_chat_thread_store

USER = ClerkUser(user_id="user_123", session_id="sess_1", claims={})
OTHER_USER = ClerkUser(user_id="user_other", session_id="sess_2", claims={})


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


class FakeThreadStore:
    def __init__(self) -> None:
        self.threads: dict[uuid.UUID, ChatThread] = {}

    def seed(self, *, user_id: str = USER.user_id, title: str = "Old chat") -> ChatThread:
        now = datetime.now(UTC)
        thread = ChatThread(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        self.threads[thread.id] = thread
        return thread

    async def create_thread(
        self,
        *,
        user_id: str,
        title: str = DEFAULT_THREAD_TITLE,
    ) -> ChatThread:
        now = datetime.now(UTC)
        thread = ChatThread(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        self.threads[thread.id] = thread
        return thread

    async def list_threads(self, *, user_id: str) -> list[ChatThread]:
        return sorted(
            (thread for thread in self.threads.values() if thread.user_id == user_id),
            key=lambda thread: thread.updated_at,
            reverse=True,
        )

    async def get_thread(
        self,
        *,
        user_id: str,
        thread_id: uuid.UUID,
    ) -> ChatThread | None:
        thread = self.threads.get(thread_id)
        if thread is None or thread.user_id != user_id:
            return None
        return thread

    async def touch_thread(
        self,
        *,
        thread_id: uuid.UUID,
        title: str | None = None,
    ) -> None:
        thread = self.threads.get(thread_id)
        if thread is None:
            return
        if title is not None:
            thread.title = title
        thread.updated_at = datetime.now(UTC)

    async def delete_thread(self, *, thread_id: uuid.UUID) -> None:
        self.threads.pop(thread_id, None)


class FakeCheckpointer:
    def __init__(self) -> None:
        self.history: dict[str, list[Any]] = {}
        self.deleted: list[str] = []

    async def aget_tuple(self, config: dict[str, Any]) -> Any:
        thread_id = config["configurable"]["thread_id"]
        messages = self.history.get(thread_id)
        if messages is None:
            return None
        return SimpleNamespace(checkpoint={"channel_values": {"messages": messages}})

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)
        self.history.pop(thread_id, None)


@contextmanager
def chat_client(
    *,
    agent: Any | None = None,
    store: FakeThreadStore | None = None,
    checkpointer: FakeCheckpointer | None = None,
    user: ClerkUser = USER,
) -> Iterator[tuple[TestClient, FakeThreadStore, FakeCheckpointer]]:
    thread_store = store or FakeThreadStore()
    checkpoint_store = checkpointer or FakeCheckpointer()
    app.dependency_overrides[require_auth] = lambda: user
    app.dependency_overrides[get_chat_agent] = lambda: agent or FakeAgent()
    app.dependency_overrides[get_chat_thread_store] = lambda: thread_store
    app.dependency_overrides[get_checkpointer] = lambda: checkpoint_store
    try:
        with TestClient(app) as client:
            yield client, thread_store, checkpoint_store
    finally:
        app.dependency_overrides.clear()


def post_with_agent(
    agent: Any,
    body: dict[str, Any],
    *,
    store: FakeThreadStore | None = None,
    user: ClerkUser = USER,
) -> Any:
    with chat_client(agent=agent, store=store, user=user) as (client, _, _):
        return client.post("/api/v1/chat", json=body)


def test_chat_returns_the_main_agent_reply() -> None:
    agent = FakeAgent()
    store = FakeThreadStore()

    response = post_with_agent(agent, {"message": "plastic ka rate kya hai?"}, store=store)

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user_123"
    assert body["reply"] == "Try selling plastic in Multan."

    thread_id = body["thread_id"]
    assert thread_id in {str(thread.id) for thread in store.threads.values()}
    call = agent.calls[0]
    message = call["payload"]["messages"][0]
    assert isinstance(message, HumanMessage)
    assert message.content == "plastic ka rate kya hai?"
    assert call["config"]["configurable"]["thread_id"] == thread_id
    assert call["config"]["configurable"]["picker_id"] == "user_123"
    assert call["context"] == AgentContext(picker_id="user_123")


def test_chat_continues_an_owned_thread() -> None:
    agent = FakeAgent()
    store = FakeThreadStore()
    thread = store.seed()

    response = post_with_agent(
        agent,
        {"message": "hello", "thread_id": str(thread.id)},
        store=store,
    )

    assert response.status_code == 200
    assert response.json()["thread_id"] == str(thread.id)
    assert agent.calls[0]["config"]["configurable"]["thread_id"] == str(thread.id)


def test_chat_rejects_another_users_thread() -> None:
    store = FakeThreadStore()
    foreign = store.seed(user_id="user_other")

    response = post_with_agent(
        FakeAgent(),
        {"message": "hello", "thread_id": str(foreign.id)},
        store=store,
    )

    assert response.status_code == 404


def test_thread_list_is_scoped_to_the_authenticated_user() -> None:
    store = FakeThreadStore()
    mine = store.seed(user_id=USER.user_id, title="Mine")
    store.seed(user_id=OTHER_USER.user_id, title="Theirs")

    with chat_client(store=store) as (client, _, _):
        response = client.get("/api/v1/chat/threads")

    assert response.status_code == 200
    assert [thread["id"] for thread in response.json()] == [str(mine.id)]


def test_create_thread_accepts_an_empty_body() -> None:
    with chat_client() as (client, store, _):
        response = client.post("/api/v1/chat/threads")

    assert response.status_code == 201
    assert response.json()["title"] == DEFAULT_THREAD_TITLE
    assert len(store.threads) == 1


def test_thread_history_is_scoped_to_the_authenticated_user() -> None:
    store = FakeThreadStore()
    checkpointer = FakeCheckpointer()
    mine = store.seed(user_id=USER.user_id)
    foreign = store.seed(user_id=OTHER_USER.user_id)
    checkpointer.history[str(mine.id)] = [
        HumanMessage(content="hello"),
        AIMessage(content="hi there"),
    ]
    checkpointer.history[str(foreign.id)] = [HumanMessage(content="secret")]

    with chat_client(store=store, checkpointer=checkpointer) as (client, _, _):
        response = client.get(f"/api/v1/chat/threads/{mine.id}/messages")
        foreign_response = client.get(f"/api/v1/chat/threads/{foreign.id}/messages")

    assert response.status_code == 200
    assert response.json() == {
        "thread_id": str(mine.id),
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ],
    }
    assert foreign_response.status_code == 404


def test_delete_thread_removes_only_owned_history() -> None:
    store = FakeThreadStore()
    checkpointer = FakeCheckpointer()
    mine = store.seed(user_id=USER.user_id)
    foreign = store.seed(user_id=OTHER_USER.user_id)

    with chat_client(store=store, checkpointer=checkpointer) as (client, _, _):
        response = client.delete(f"/api/v1/chat/threads/{mine.id}")
        foreign_response = client.delete(f"/api/v1/chat/threads/{foreign.id}")

    assert response.status_code == 204
    assert foreign_response.status_code == 404
    assert mine.id not in store.threads
    assert foreign.id in store.threads
    assert checkpointer.deleted == [str(mine.id)]


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
