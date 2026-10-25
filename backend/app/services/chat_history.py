"""Read user-facing messages back from the agent's graph state."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.schemas.chat import ThreadMessage


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
            else:
                text = getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts).strip()
    return ""


async def load_thread_messages(
    graph: Any,
    *,
    thread_id: str,
) -> list[ThreadMessage]:
    """Return only human/assistant turns for a single checkpoint thread.

    The graph state is read through ``aget_state`` rather than the raw
    checkpointer because message channels are stored as deltas and only the
    graph can resolve them into the full message list.
    """
    state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    values = getattr(state, "values", None) or {}
    raw_messages = values.get("messages") or []

    messages: list[ThreadMessage] = []
    for message in raw_messages:
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            continue

        text = _text_from_content(message.content)
        if text:
            messages.append(ThreadMessage(role=role, content=text))

    return messages
