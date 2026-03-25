"""Marketing content generation proxy endpoint."""

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from biotact.core.dependencies import CurrentUserDep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/marketing", tags=["marketing"])

CONTENT_AGENT_URL = "http://content-agent-api:8001"
REQUEST_TIMEOUT = 30.0


class GenerateRequest(BaseModel):
    """Content generation request."""

    product: str = Field(min_length=1, max_length=200)
    context: str | None = Field(default=None, max_length=500)


class VariantResponse(BaseModel):
    """Single post variant."""

    text: str
    is_blocked: bool
    stop_words_found: list[str]
    warnings: list[str]
    replacements_made: list[str]


class GenerateResponse(BaseModel):
    """Content generation response."""

    variants: list[VariantResponse]
    model_used: str
    error: str | None = None


@router.post("/generate", response_model=GenerateResponse)
async def generate_content(
    current_user: CurrentUserDep,
    req: GenerateRequest,
) -> GenerateResponse:
    """Generate 2 post variants for a BIOTACT product.

    Proxies request to content-agent-api on internal Docker network.
    """
    logger.info(
        "Content generation: user=%s product=%r",
        current_user.email,
        req.product,
    )

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{CONTENT_AGENT_URL}/generate",
                json=req.model_dump(exclude_none=True),
            )
            response.raise_for_status()
    except httpx.TimeoutException as e:
        raise HTTPException(
            status_code=504,
            detail="Content generation timed out. Try again.",
        ) from e
    except httpx.HTTPError as e:
        logger.exception("content-agent-api request failed")
        raise HTTPException(
            status_code=502,
            detail="Content generation service unavailable.",
        ) from e

    return GenerateResponse(**response.json())


class HistoryItem(BaseModel):
    """Single history entry."""

    id: int
    product: str
    context: str | None
    variant_1: str
    variant_2: str | None
    model_used: str | None
    warnings: list[str]
    channel: str
    user_id: str | None
    created_at: str


@router.get("/history", response_model=list[HistoryItem])
async def get_history(
    current_user: CurrentUserDep,
    product: str | None = None,
    days: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[HistoryItem]:
    """Get content generation history. Proxies to content-agent-api."""
    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    if product:
        params["product"] = product
    if days:
        params["days"] = days

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{CONTENT_AGENT_URL}/history",
                params=params,
            )
            response.raise_for_status()
    except httpx.HTTPError as e:
        logger.exception("content-agent-api history request failed")
        raise HTTPException(status_code=502, detail="History unavailable.") from e

    return [HistoryItem(**item) for item in response.json()]


class ChatMessage(BaseModel):
    """Chat message."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Marketing chat request."""

    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessage] | None = None


class ChatAction(BaseModel):
    """Action for frontend."""

    type: str
    params: dict[str, object] | None = None
    data: dict[str, object] | None = None


class ChatResponse(BaseModel):
    """Chat response."""

    message: str
    action: ChatAction | None = None


@router.post("/chat", response_model=ChatResponse)
async def marketing_chat(
    current_user: CurrentUserDep,
    req: ChatRequest,
) -> ChatResponse:
    """Marketing AI chat with function calling. Proxies to content-agent-api."""
    logger.info(
        "Marketing chat: user=%s message=%r", current_user.email, req.message[:50]
    )

    body: dict[str, object] = {"message": req.message}
    if req.history:
        body["history"] = [h.model_dump() for h in req.history]

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{CONTENT_AGENT_URL}/chat",
                json=body,
            )
            response.raise_for_status()
    except httpx.TimeoutException as e:
        raise HTTPException(status_code=504, detail="Chat timed out.") from e
    except httpx.HTTPError as e:
        logger.exception("content-agent-api chat failed")
        raise HTTPException(status_code=502, detail="Chat unavailable.") from e

    data = response.json()
    action = ChatAction(**data["action"]) if data.get("action") else None
    return ChatResponse(message=data["message"], action=action)
