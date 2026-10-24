"""Request and response schemas for the picker chat endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=4000)
    thread_id: UUID | None = None


class ChatResponse(BaseModel):
    user_id: str
    thread_id: UUID
    reply: str


class ChatThreadCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)


class ChatThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ThreadMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatThreadHistory(BaseModel):
    thread_id: UUID
    messages: list[ThreadMessage]
