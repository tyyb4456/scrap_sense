"""Chat endpoints for picker conversations and their isolated threads."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.main_agent import AgentContext, aget_agent, aget_checkpointer
from app.auth import ClerkUser, require_auth
from app.models.chat_thread import DEFAULT_THREAD_TITLE, ChatThread
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatThreadCreate,
    ChatThreadHistory,
    ChatThreadRead,
)
from app.services.chat_history import load_thread_messages
from app.services.chat_threads import ChatThreadStore, get_chat_thread_store

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


async def get_checkpointer() -> Any:
    """Return the shared checkpoint store (overridable in tests)."""
    try:
        return await aget_checkpointer()
    except Exception:
        logger.exception("Could not initialize checkpoint storage")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ScrapSense history is unavailable",
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


def _thread_title(message: str) -> str:
    compact = " ".join(message.split())
    return compact[:80] or DEFAULT_THREAD_TITLE


async def _owned_thread(
    *,
    store: ChatThreadStore,
    user_id: str,
    thread_id: uuid.UUID,
) -> ChatThread:
    thread = await store.get_thread(user_id=user_id, thread_id=thread_id)
    if thread is None:
        # Do not reveal whether a thread exists for another user.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat thread not found",
        )
    return thread


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: Annotated[ClerkUser, Depends(require_auth)],
    agent: Annotated[Any, Depends(get_chat_agent)],
    store: Annotated[ChatThreadStore, Depends(get_chat_thread_store)],
) -> ChatResponse:
    if payload.thread_id is None:
        thread = await store.create_thread(
            user_id=user.user_id,
            title=_thread_title(payload.message),
        )
    else:
        thread = await _owned_thread(
            store=store,
            user_id=user.user_id,
            thread_id=payload.thread_id,
        )

    thread_id = str(thread.id)

    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=payload.message)]},
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "picker_id": user.user_id,
                }
            },
            context=AgentContext(picker_id=user.user_id),
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

    title = _thread_title(payload.message) if thread.title == DEFAULT_THREAD_TITLE else None
    await store.touch_thread(thread_id=thread.id, title=title)

    return ChatResponse(user_id=user.user_id, thread_id=thread.id, reply=reply)


@router.get("/threads", response_model=list[ChatThreadRead])
async def list_threads(
    user: Annotated[ClerkUser, Depends(require_auth)],
    store: Annotated[ChatThreadStore, Depends(get_chat_thread_store)],
) -> list[ChatThreadRead]:
    threads = await store.list_threads(user_id=user.user_id)
    return [ChatThreadRead.model_validate(thread) for thread in threads]


@router.post(
    "/threads",
    response_model=ChatThreadRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread(
    user: Annotated[ClerkUser, Depends(require_auth)],
    store: Annotated[ChatThreadStore, Depends(get_chat_thread_store)],
    payload: ChatThreadCreate | None = None,
) -> ChatThreadRead:
    title = payload.title if payload and payload.title else DEFAULT_THREAD_TITLE
    thread = await store.create_thread(user_id=user.user_id, title=title)
    return ChatThreadRead.model_validate(thread)


@router.get("/threads/{thread_id}/messages", response_model=ChatThreadHistory)
async def get_thread_messages(
    thread_id: uuid.UUID,
    user: Annotated[ClerkUser, Depends(require_auth)],
    store: Annotated[ChatThreadStore, Depends(get_chat_thread_store)],
    checkpointer: Annotated[Any, Depends(get_checkpointer)],
) -> ChatThreadHistory:
    thread = await _owned_thread(
        store=store,
        user_id=user.user_id,
        thread_id=thread_id,
    )
    messages = await load_thread_messages(checkpointer, thread_id=str(thread.id))
    return ChatThreadHistory(thread_id=thread.id, messages=messages)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: uuid.UUID,
    user: Annotated[ClerkUser, Depends(require_auth)],
    store: Annotated[ChatThreadStore, Depends(get_chat_thread_store)],
    checkpointer: Annotated[Any, Depends(get_checkpointer)],
) -> Response:
    thread = await _owned_thread(
        store=store,
        user_id=user.user_id,
        thread_id=thread_id,
    )

    try:
        await checkpointer.adelete_thread(str(thread.id))
    except Exception:
        logger.exception("Could not delete chat checkpoints")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not delete chat history",
        ) from None

    await store.delete_thread(thread_id=thread.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
