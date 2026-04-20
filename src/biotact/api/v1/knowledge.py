"""Public Knowledge API — search across all Qdrant collections.

Designed for Claude Code terminal access. Auth via X-API-Key header.
Searches: knowledge-evolution, user_files, dr_berg in parallel.
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient

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
    "nutrition": {
        "name": "nutrition_library",
        "text_field": "content",
        "source_label": "nutrition_library",
    },
    "medical": {
        "name": "medical_sources",
        "text_field": "content",
        "source_label": "medical_sources",
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


async def _translate_to_english(text: str) -> str:
    """Translate query to English for English-only collections (dr_berg).

    Costs ~$0.001 per query. Skips if already English.
    """
    from openai import AsyncOpenAI

    # Quick heuristic: if mostly ASCII, probably already English
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii < len(text) * 0.3:
        return text

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model="gpt-4.1-nano",
            max_completion_tokens=200,
            messages=[
                {
                    "role": "system",
                    "content": "Translate the following search query to English. "
                    "Return ONLY the translation, nothing else.",
                },
                {"role": "user", "content": text},
            ],
        )
        translated = (response.choices[0].message.content or text).strip()
        logger.info("Translated query: '%s' → '%s'", text, translated)
        return translated
    except Exception:
        logger.warning("Translation failed, using original query")
        return text


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
    point: Any, config: dict[str, str],
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
    source: str | None = Query(None, description="Filter: biotact, files, dr_berg, nutrition"),
    limit: int = Query(10, ge=1, le=50),
    threshold: float = Query(0.3, ge=0.0, le=1.0),
    x_api_key: str = Header(...),
) -> SearchResponse:
    """Search across all knowledge collections.

    - **q**: Natural language query
    - **source**: Optional filter (biotact, files, dr_berg, nutrition)
    - **limit**: Max results per collection
    - **threshold**: Minimum similarity score (0-1)
    """
    _verify_api_key(x_api_key)

    # Determine which collections to search
    if source and source in COLLECTIONS:
        targets = {source: COLLECTIONS[source]}
    else:
        targets = COLLECTIONS

    # Prepare embeddings: translated for English collections, original for Russian
    query_en = await _translate_to_english(q) if q != q.encode("ascii", "ignore").decode() else q
    embedding_original = await _get_embedding(q)
    embedding_en = await _get_embedding(query_en) if query_en != q else embedding_original

    # Search all collections
    qdrant = _get_qdrant()
    all_results: list[SearchResult] = []

    for _key, config in targets.items():
        # Use English embedding for English collections, original for Russian
        use_en = config["source_label"] in ("dr_berg", "nutrition_library", "medical_sources")
        embedding = embedding_en if use_en else embedding_original

        try:
            response = await qdrant.query_points(
                collection_name=config["name"],
                query=embedding,
                limit=limit,
                score_threshold=threshold,
            )
            for point in response.points:
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


# Transcript directory on server
TRANSCRIPT_DIR = Path("/opt/berg-knowledge/data/transcripts")


@router.get("/transcript/{video_id}")
async def get_transcript(
    video_id: str,
    x_api_key: str = Header(...),
) -> dict[str, Any]:
    """Get full transcript for a Dr. Berg video by video_id.

    Full texts stored on disk, not in Qdrant (too large for chunks).
    """
    _verify_api_key(x_api_key)

    # Try common filename patterns
    for pattern in [f"*{video_id}*"]:
        matches = list(TRANSCRIPT_DIR.glob(pattern)) if TRANSCRIPT_DIR.exists() else []
        if matches:
            file_path = matches[0]
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return {
                "video_id": video_id,
                "file_name": file_path.name,
                "content": text,
                "size": len(text),
            }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Transcript not found for video_id: {video_id}",
    )
