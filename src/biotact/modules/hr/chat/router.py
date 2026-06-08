"""HR Chat API endpoint."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import get_settings
from biotact.core.database import get_session
from biotact.core.dependencies import RequireHREmailDep
from biotact.modules.hr.chat.schemas import HRChatRequest, HRChatResponse
from biotact.modules.hr.chat.service import HRChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr/chat", tags=["hr-chat"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/message", response_model=HRChatResponse)
async def hr_chat_message(
    req: HRChatRequest,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> HRChatResponse:
    """Send message to HR AI assistant. Returns text + optional document."""
    logger.info("HR chat: user=%s message=%r", current_user.email, req.message[:80])
    settings = get_settings()
    service = HRChatService(settings, db, user_id=current_user.id)
    result: dict[str, Any] = await service.process_message(req.message, req.history)
    return HRChatResponse(
        message=result["message"],
        document_url=result.get("document_url"),
    )
