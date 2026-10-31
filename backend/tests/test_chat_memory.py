from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from langgraph.store.base import BaseStore

from app.agents.main_agent import memory_namespace
from app.services.chat_memory import delete_picker_memory


class FakeStore:
    def __init__(self) -> None:
        self.items: dict[tuple[str, ...], dict[str, Any]] = {}

    async def asearch(
        self,
        namespace: tuple[str, ...],
        *,
        limit: int = 10,
        offset: int = 0,
        **_kwargs: Any,
    ) -> list[SimpleNamespace]:
        keys = sorted(self.items.get(namespace, {}))
        return [
            SimpleNamespace(key=key, value=self.items[namespace][key])
            for key in keys[offset : offset + limit]
        ]

    async def adelete(self, namespace: tuple[str, ...], key: str) -> None:
        self.items.get(namespace, {}).pop(key, None)


def test_memory_namespace_is_scoped_to_one_picker() -> None:
    assert memory_namespace("user_a") == ("user_a",)
    assert memory_namespace("user_a") != memory_namespace("user_b")


async def test_delete_picker_memory_removes_only_the_requested_namespace() -> None:
    store = FakeStore()
    store.items[memory_namespace("user_a")] = {
        "/picker_notes.md": {"content": "a"},
        "/other.md": {"content": "a2"},
    }
    store.items[memory_namespace("user_b")] = {
        "/picker_notes.md": {"content": "b"},
    }

    deleted = await delete_picker_memory(store=cast(BaseStore, store), picker_id="user_a")

    assert deleted == 2
    assert store.items[memory_namespace("user_a")] == {}
    assert store.items[memory_namespace("user_b")] == {
        "/picker_notes.md": {"content": "b"},
    }


async def test_delete_picker_memory_deletes_every_page() -> None:
    store = FakeStore()
    store.items[memory_namespace("user_a")] = {
        f"/note-{index}.md": {"content": str(index)} for index in range(250)
    }

    deleted = await delete_picker_memory(store=cast(BaseStore, store), picker_id="user_a")

    assert deleted == 250
    assert store.items[memory_namespace("user_a")] == {}


async def test_delete_picker_memory_is_idempotent() -> None:
    store = FakeStore()
    store.items[memory_namespace("user_a")] = {
        "/picker_notes.md": {"content": "a"},
    }

    assert await delete_picker_memory(store=cast(BaseStore, store), picker_id="user_a") == 1
    assert await delete_picker_memory(store=cast(BaseStore, store), picker_id="user_a") == 0

