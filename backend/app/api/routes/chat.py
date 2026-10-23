"""Chat endpoint that lets a picker talk to the ScrapSense main agent."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.main_agent import AgentContext, aget_agent
from app.auth import ClerkUser, require_auth
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


async def get_chat_agent() -> Any:
    """Return the lazily built main agent (overridable in tests)."""
    try:
        return await aget_agent()
    except Exception:
        logger.exception("Could not initialize the ScrapSense agent")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ScrapSense agent is unavailable",
        ) from None


def _reply_text(messages: list[Any]) -> str:
    """Return the last non-empty assistant text from an agent result."""
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        content = message.content
        if isinstance(content, str) and content.strip():
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
            joined = "".join(parts).strip()
            if joined:
                return joined
    return ""


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: Annotated[ClerkUser, Depends(require_auth)],
    agent: Annotated[Any, Depends(get_chat_agent)],
) -> ChatResponse:
    thread_id = user.user_id

    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=payload.message)]},
            config={"configurable": {"thread_id": thread_id}},
            context=AgentContext(picker_id=thread_id),
        )
    except Exception:
        logger.exception("Chat agent invocation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ScrapSense agent is unavailable",
        ) from None

    reply = _reply_text(result.get("messages", []))
    if not reply:
        logger.warning("Chat agent returned no assistant text")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ScrapSense agent returned an empty reply",
        )

    return ChatResponse(user_id=thread_id, reply=reply)
