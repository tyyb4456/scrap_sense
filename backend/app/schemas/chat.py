"""Request and response schemas for the picker chat endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    user_id: str
    reply: str
