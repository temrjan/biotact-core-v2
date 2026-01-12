"""Chat endpoints."""

from fastapi import APIRouter, Query

from biotact.core.dependencies import ChatServiceDep, CurrentUserDep
from biotact.schemas.chat import (
    ChatQueryRequest,
    ChatQueryResponse,
    ChatSessionsResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query", response_model=ChatQueryResponse)
async def chat_query(
    request: ChatQueryRequest,
    current_user: CurrentUserDep,
    chat_service: ChatServiceDep,
) -> ChatQueryResponse:
    """Send a chat query to the RAG system.

    - **message**: User's question (1-4000 chars)
    - **session_id**: Optional session ID to continue conversation
    """
    return await chat_service.query(
        user_id=current_user.id,
        department_id=current_user.department_id,
        message=request.message,
        session_id=request.session_id,
    )


@router.get("/sessions", response_model=ChatSessionsResponse)
async def get_sessions(
    current_user: CurrentUserDep,
    chat_service: ChatServiceDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChatSessionsResponse:
    """Get user's chat sessions with pagination.

    - **limit**: Maximum number of sessions to return (1-100)
    - **offset**: Number of sessions to skip
    """
    return await chat_service.get_sessions(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
