"""Chat schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatQueryRequest(BaseModel):
    """Schema for chat query request."""

    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class Source(BaseModel):
    """Schema for RAG source document."""

    id: str
    title: str
    relevance_score: float = Field(ge=0, le=1)


class ActionResult(BaseModel):
    """Schema for command action result."""

    type: str
    success: bool
    data: dict[str, Any] | None = None


class ChatQueryResponse(BaseModel):
    """Schema for chat query response."""

    answer: str
    sources: list[Source]
    session_id: str
    message_id: str
    action_result: ActionResult | None = None


class ChatSessionResponse(BaseModel):
    """Schema for chat session."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int

    model_config = {"from_attributes": True}


class ChatSessionsResponse(BaseModel):
    """Schema for list of chat sessions."""

    sessions: list[ChatSessionResponse]
    total: int
    limit: int
    offset: int
