"""Public API endpoints for external bot integration.

Thin adapter: validates API key, delegates to AskBiotactService.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status

from biotact.core.config import get_settings
from biotact.modules.askbiotact.schemas import AskRequest, AskResponse, UserInfo
from biotact.modules.askbiotact.service import get_askbiotact_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])

settings = get_settings()


def _verify_api_key(x_api_key: str) -> None:
    if x_api_key != settings.askbiotact_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


@router.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> AskResponse:
    """Process a question through AskBiotact RAG system."""
    _verify_api_key(x_api_key)

    service = get_askbiotact_service()

    # Get AI response (CRM + enrichment + RAG + extraction agent)
    answer = await service.get_ai_response(
        user_id=request.user_id,
        message=request.message,
        history_prefix="public",
        first_name=request.first_name,
        username=request.username,
    )

    # Order detection with dedup
    order_sent = False
    if not await service.is_order_already_sent(request.user_id):
        history = await service.get_chat_history(request.user_id, "public")
        order_data = service.detect_order(request.message, history)
        if order_data:
            user_info = UserInfo(
                user_id=request.user_id,
                first_name=request.first_name or "",
                username=request.username or "нет",
            )
            order_sent = await service.send_order_to_sales(
                order_data,
                user_info,
                history,
            )
            if order_sent:
                await service.mark_order_sent(request.user_id)

    return AskResponse(
        answer=answer,
        user_id=request.user_id,
        order_sent=order_sent,
    )


@router.post("/ask/reset")
async def reset_history(
    user_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> dict[str, Any]:
    """Reset chat history for a user."""
    _verify_api_key(x_api_key)

    try:
        service = get_askbiotact_service()
        await service.reset_conversation(user_id, "public")
        return {"ok": True, "message": "History cleared"}
    except Exception as e:
        logger.error("Reset error: %s", e)
        return {"ok": False, "message": str(e)}
