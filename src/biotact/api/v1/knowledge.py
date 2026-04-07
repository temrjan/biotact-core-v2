"""Public Knowledge API — search across all Qdrant collections.

Designed for Claude Code terminal access. Auth via X-API-Key header.
Searches: knowledge-evolution, user_files, dr_berg in parallel.
"""

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    ScoredPoint,
)

from biotact.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge-public"])

# Collections to search
COLLECTIONS = {
    "biotact": {
        "name": "knowledge-evolution",
        "text_field": "content",
        "source_label": "biotact",
    },
    "files": {
        "name": "user_files",
        "text_field": "content",
        "source_label": "user_files",
    },
    "dr_berg": {
        "name": "dr_berg",
        "text_field": "content",  # dr_berg uses "text" for old data, "content" for new
        "text_field_alt": "text",
        "source_label": "dr_berg",
    },
}


# ═══════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════


class SearchResult(BaseModel):
    """Single search result."""

    content: str
    source: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Search response."""

    query: str
    results: list[SearchResult]
    total: int


class DocumentResponse(BaseModel):
    """Full document/chunk detail."""

    id: str
    content: str
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StatsResponse(BaseModel):
    """Collection statistics."""

    collections: dict[str, int]
    total_points: int


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

API_KEY_SETTING = "askbiotact_api_key"  # reuse existing key from config


def _verify_api_key(x_api_key: str) -> None:
    """Verify API key."""
    settings = get_settings()
    expected = getattr(settings, API_KEY_SETTING, "")
    if not expected or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def _get_qdrant() -> AsyncQdrantClient:
    """Get async Qdrant client."""
    settings = get_settings()
    return AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=settings.qdrant_api_key,
    )


async def _get_embedding(text: str) -> list[float]:
    """Get embedding via OpenAI."""
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=text,
    )
    return response.data[0].embedding


def _extract_content(payload: dict[str, Any], config: dict[str, str]) -> str:
    """Extract text content from payload, handling field name differences."""
    text = payload.get(config["text_field"], "")
    if not text and "text_field_alt" in config:
        text = payload.get(config["text_field_alt"], "")
    return str(text)


def _point_to_result(
    point: ScoredPoint, config: dict[str, str],
) -> SearchResult:
    """Convert Qdrant point to SearchResult."""
    payload = point.payload or {}
    content = _extract_content(payload, config)

    # Build metadata (everything except the text field)
    metadata = {
        k: v
        for k, v in payload.items()
        if k not in (config["text_field"], config.get("text_field_alt", ""))
    }

    return SearchResult(
        content=content,
        source=payload.get("source", config["source_label"]),
        score=round(point.score, 4),
        metadata=metadata,
    )


# ═══════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════


@router.get("/search", response_model=SearchResponse)
async def search_knowledge(
    q: str = Query(..., min_length=1, description="Search query"),
    source: str | None = Query(None, description="Filter: biotact, files, dr_berg"),
    limit: int = Query(10, ge=1, le=50),
    threshold: float = Query(0.3, ge=0.0, le=1.0),
    x_api_key: str = Header(...),
) -> SearchResponse:
    """Search across all knowledge collections.

    - **q**: Natural language query
    - **source**: Optional filter (biotact, files, dr_berg)
    - **limit**: Max results per collection
    - **threshold**: Minimum similarity score (0-1)
    """
    _verify_api_key(x_api_key)

    # Embed query
    embedding = await _get_embedding(q)

    # Determine which collections to search
    if source and source in COLLECTIONS:
        targets = {source: COLLECTIONS[source]}
    else:
        targets = COLLECTIONS

    # Search all collections in parallel
    qdrant = _get_qdrant()
    all_results: list[SearchResult] = []

    for _key, config in targets.items():
        try:
            points = await qdrant.search(
                collection_name=config["name"],
                query_vector=embedding,
                limit=limit,
                score_threshold=threshold,
            )
            for point in points:
                all_results.append(_point_to_result(point, config))
        except Exception as e:
            logger.warning("Search failed for %s: %s", config["name"], e)

    await qdrant.close()

    # Sort by score descending, take top N
    all_results.sort(key=lambda r: r.score, reverse=True)
    top_results = all_results[:limit]

    return SearchResponse(
        query=q,
        results=top_results,
        total=len(top_results),
    )


@router.get("/stats", response_model=StatsResponse)
async def knowledge_stats(
    x_api_key: str = Header(...),
) -> StatsResponse:
    """Get point counts for all collections."""
    _verify_api_key(x_api_key)

    qdrant = _get_qdrant()
    counts: dict[str, int] = {}

    for key, config in COLLECTIONS.items():
        try:
            info = await qdrant.get_collection(config["name"])
            counts[key] = info.points_count or 0
        except Exception:
            counts[key] = 0

    await qdrant.close()

    return StatsResponse(
        collections=counts,
        total_points=sum(counts.values()),
    )


@router.get("/collections", response_model=dict[str, Any])
async def list_collections(
    x_api_key: str = Header(...),
) -> dict[str, Any]:
    """List available collections and their config."""
    _verify_api_key(x_api_key)

    return {
        "collections": {
            key: {
                "qdrant_name": config["name"],
                "text_field": config["text_field"],
                "source": config["source_label"],
            }
            for key, config in COLLECTIONS.items()
        }
    }
