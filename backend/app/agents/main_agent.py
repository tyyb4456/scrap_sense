"""
ScrapSense main agent definition and orchestration.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, NotRequired, cast

from deepagents import DeepAgentState, create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import BaseStore
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agents.report_intaker import scrap_pipeline_agent
from app.core.config import Settings, get_settings
from app.llm import build_xkiro_llm
from app.tools.price_estimator import estimate_price

logger = logging.getLogger(__name__)

MEMORY_FILE_PATH = "/memories/picker_notes.md"

SYSTEM_PROMPT = f"""
You are ScrapSense, a helpful copilot for waste pickers.

Your job:
- Understand the picker's message in whatever language or mix of languages they use.
- When they report a scrap sale, delegate the raw message to the
  `scrap_report_pipeline` subagent. Do not invent or rewrite the sale details.
- If the subagent asks for clarification, relay that question back to the picker
  in a short, friendly way.
- When they ask what a material is worth, use the `estimate_price` tool.
- Keep {MEMORY_FILE_PATH} up to date with useful facts the picker shares,
  such as their usual area or the materials they collect.

Be concise and practical.
""".strip()


def memory_namespace(picker_id: str) -> tuple[str, ...]:
    """Return the persistent store namespace for one picker's long-term notes."""
    return (picker_id,)


class MainAgentState(DeepAgentState):
    """Coordinator state carrying the verbatim picker message.

    This field is set from the authenticated request at the chat boundary and is
    propagated by Deep Agents into the compiled report-intake subagent. It is
    never derived from the coordinator's task description.
    """

    original_message: NotRequired[str | None]


@dataclass
class AgentContext:
    """Runtime context passed to agent execution per-request."""

    picker_id: str


def build_agent(
    *,
    settings: Settings,
    store: BaseStore,
    checkpointer: BaseCheckpointSaver,
) -> Any:
    """Build the ScrapSense coordinator with backed memory and checkpoints."""
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/memories/": StoreBackend(
                namespace=lambda rt: memory_namespace(rt.context.picker_id),
                store=store,
            ),
        },
    )

    logger.info("Initializing ScrapSense deep agent with model %s", settings.xkiro_model)
    return create_deep_agent(
        model=build_xkiro_llm(settings=settings),
        system_prompt=SYSTEM_PROMPT,
        state_schema=MainAgentState,
        subagents=[scrap_pipeline_agent],
        tools=[estimate_price],
        context_schema=AgentContext,
        checkpointer=checkpointer,
        store=store,
        backend=backend,
        memory=[MEMORY_FILE_PATH],
    )


_agent: Any = None
_pool: AsyncConnectionPool[AsyncConnection[dict[str, Any]]] | None = None
_checkpointer: BaseCheckpointSaver | None = None
_store: BaseStore | None = None
_lock = asyncio.Lock()


async def aget_agent() -> Any:
    """Open the shared Postgres pool and build the agent on first use."""
    global _agent, _pool, _checkpointer, _store

    if _agent is not None:
        return _agent

    async with _lock:
        if _agent is not None:
            return _agent

        settings = get_settings()
        pool = cast(
            AsyncConnectionPool[AsyncConnection[dict[str, Any]]],
            AsyncConnectionPool(
                conninfo=settings.postgres_uri,
                max_size=10,
                open=False,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
            ),
        )
        await pool.open()

        try:
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()

            store = AsyncPostgresStore(pool)
            await store.setup()

            agent = build_agent(
                settings=settings,
                store=store,
                checkpointer=checkpointer,
            )
        except BaseException:
            await pool.close()
            raise

        _pool = pool
        _agent = agent
        _checkpointer = checkpointer
        _store = store
        logger.info("Deep agent initialized successfully with a shared Postgres pool.")
        return _agent


async def aget_checkpointer() -> BaseCheckpointSaver:
    """Return the shared checkpointer, initializing the agent if needed."""
    if _checkpointer is None:
        await aget_agent()
    if _checkpointer is None:
        raise RuntimeError("Checkpoint storage is unavailable")
    return _checkpointer


async def aget_store() -> BaseStore:
    """Return the shared long-term memory store, initializing the agent if needed."""
    if _store is None:
        await aget_agent()
    if _store is None:
        raise RuntimeError("Long-term memory storage is unavailable")
    return _store


async def aclose_agent() -> None:
    """Close the shared Postgres pool when the application shuts down."""
    global _agent, _pool, _checkpointer, _store

    async with _lock:
        if _pool is not None:
            await _pool.close()
        _pool = None
        _agent = None
        _checkpointer = None
        _store = None


if __name__ == "__main__":
    from langchain_core.messages import HumanMessage

    async def _smoke_test() -> None:
        agent = await aget_agent()
        try:
            result = await agent.ainvoke(
                {
                    "messages": [
                        HumanMessage(
                            content=(
                                "bhai maine aaj do kilo plastic becha, teen sau rupay mila, "
                                "income colony ke qareeb"
                            )
                        )
                    ]
                },
                config={"configurable": {"thread_id": "smoke-test-picker"}},
                context=AgentContext(picker_id="smoke-test-picker"),
            )
            print("Agent execution result:", result)
        finally:
            await aclose_agent()

    asyncio.run(_smoke_test())
