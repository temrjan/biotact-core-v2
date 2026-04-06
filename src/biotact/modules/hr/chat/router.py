"""HR Chat API endpoint."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import get_settings
from biotact.core.database import get_session
from biotact.core.dependencies import CurrentUserDep
from biotact.modules.hr.chat.service import HRChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr/chat", tags=["hr-chat"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class HRChatRequest(BaseModel):
    """Chat request from frontend."""

    message: str = Field(min_length=1, max_length=5000)
    history: list[dict[str, str]] | None = None


class HRChatResponse(BaseModel):
    """Chat response with optional document text."""

    message: str
    document_text: str | None = None


@router.post("/message", response_model=HRChatResponse)
async def hr_chat_message(
    req: HRChatRequest,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> HRChatResponse:
    """Send message to HR AI assistant. Returns text + optional document."""
    logger.info("HR chat: user=%s message=%r", current_user.email, req.message[:80])
    settings = get_settings()
    service = HRChatService(settings, db)
    result: dict[str, Any] = await service.process_message(req.message, req.history)
    return HRChatResponse(
        message=result["message"],
        document_text=result.get("document_text"),
    )
