"""HR Chat Pydantic schemas.

Kept separate from router.py so chat/service.py can type-annotate history
messages without circular imports.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """One chat history entry from the client.

    role is constrained so the client cannot forge `system` or `tool`
    messages to override server-side prompts (closes prompt injection
    via crafted history).
    """

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=5000)


class HRChatRequest(BaseModel):
    """Chat request from frontend."""

    message: str = Field(min_length=1, max_length=5000)
    history: list[ChatMessage] | None = Field(default=None, max_length=20)


class HRChatResponse(BaseModel):
    """Chat response with optional document URL."""

    message: str
    document_url: str | None = None
