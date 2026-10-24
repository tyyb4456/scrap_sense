"""Persistence helpers for user-owned chat threads."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.chat_thread import DEFAULT_THREAD_TITLE, ChatThread


class ChatThreadStore:
    """All thread reads and writes go through the authenticated user's id."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_thread(
        self,
        *,
        user_id: str,
        title: str = DEFAULT_THREAD_TITLE,
    ) -> ChatThread:
        thread = ChatThread(user_id=user_id, title=title)
        self._session.add(thread)
        await self._session.commit()
        await self._session.refresh(thread)
        return thread

    async def list_threads(self, *, user_id: str) -> list[ChatThread]:
        result = await self._session.execute(
            select(ChatThread)
            .where(ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.desc(), ChatThread.created_at.desc())
        )
        return list(result.scalars())

    async def get_thread(
        self,
        *,
        user_id: str,
        thread_id: uuid.UUID,
    ) -> ChatThread | None:
        """Return the thread only when it belongs to this user."""
        result = await self._session.execute(
            select(ChatThread).where(
                ChatThread.id == thread_id,
                ChatThread.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def touch_thread(
        self,
        *,
        thread_id: uuid.UUID,
        title: str | None = None,
    ) -> None:
        values: dict[str, object] = {"updated_at": func.now()}
        if title is not None:
            values["title"] = title
        await self._session.execute(
            update(ChatThread).where(ChatThread.id == thread_id).values(**values)
        )
        await self._session.commit()

    async def delete_thread(self, *, thread_id: uuid.UUID) -> None:
        await self._session.execute(delete(ChatThread).where(ChatThread.id == thread_id))
        await self._session.commit()


def get_chat_thread_store(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatThreadStore:
    return ChatThreadStore(session)
