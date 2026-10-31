"""Deletion helpers for a picker's long-term agent memory."""

from __future__ import annotations

from langgraph.store.base import BaseStore

from app.agents.main_agent import memory_namespace

_PAGE_SIZE = 100
_MAX_PAGES = 1000


async def delete_picker_memory(*, store: BaseStore, picker_id: str) -> int:
    """Delete every stored memory item in the picker's namespace.

    Long-term memory lives in a per-picker namespace and is shared across that
    picker's chat threads. Deleting a single thread therefore cannot remove it;
    this function is the explicit erasure path. It is idempotent and returns the
    number of deleted store items.
    """
    namespace = memory_namespace(picker_id)
    deleted = 0

    for _ in range(_MAX_PAGES):
        items = await store.asearch(namespace, limit=_PAGE_SIZE)
        if not items:
            return deleted
        for item in items:
            await store.adelete(namespace, item.key)
            deleted += 1

    raise RuntimeError("Long-term memory deletion did not complete")
