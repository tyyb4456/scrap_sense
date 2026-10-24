"""Server-owned conversation threads for the picker chat."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DEFAULT_THREAD_TITLE = "New chat"


class ChatThread(Base):
    """A conversation owned by exactly one authenticated Clerk user."""

    __tablename__ = "chat_threads"
    __table_args__ = (
        Index("ix_chat_threads_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default=DEFAULT_THREAD_TITLE,
        server_default=DEFAULT_THREAD_TITLE,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
