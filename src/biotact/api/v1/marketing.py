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
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Content generation timed out. Try again.",
        )
    except httpx.HTTPError as e:
        logger.exception("content-agent-api request failed")
        raise HTTPException(
            status_code=502,
            detail="Content generation service unavailable.",
        ) from e

    return GenerateResponse(**response.json())
