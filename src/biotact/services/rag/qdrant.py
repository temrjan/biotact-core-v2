"""Qdrant service for vector search operations."""

import json
import logging
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, ScoredPoint

from biotact.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Search result from Qdrant."""

    content: str
    score: float
    source: str
    metadata: dict[str, str | int | float | bool]


class QdrantService:
    """Service for vector search operations with Qdrant.

    Implements payload-based multitenancy using department_id filter.
    """

    def __init__(self, settings: Settings) -> None:
        self.client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )
        self.collection = settings.qdrant_collection

    async def search(
        self,
        query_vector: list[float],
        department_id: str,
        limit: int = 5,
        score_threshold: float = 0.7,
    ) -> list[SearchResult]:
        """Search for similar documents with department filtering.

        Args:
            query_vector: Query embedding vector.
            department_id: Department ID for multitenancy filtering.
            limit: Maximum number of results.
            score_threshold: Minimum similarity score.

        Returns:
            List of search results with content and metadata.
        """
        # Build filter for department-based multitenancy
        search_filter = Filter(
            must=[
                FieldCondition(
                    key="department_id",
                    match=MatchValue(value=department_id),
                )
            ]
        )

        response = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=search_filter,
            limit=limit,
            score_threshold=score_threshold,
        )

        return [self._point_to_result(point) for point in response.points]

    async def search_all_departments(
        self,
        query_vector: list[float],
        limit: int = 5,
        score_threshold: float = 0.7,
    ) -> list[SearchResult]:
        """Search across all departments (for admin users).

        Args:
            query_vector: Query embedding vector.
            limit: Maximum number of results.
            score_threshold: Minimum similarity score.

        Returns:
            List of search results.
        """
        response = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold,
        )

        logger.info(f"Qdrant search: found {len(response.points)} points")
        for p in response.points:
            logger.info(f"  Point score: {p.score}, payload keys: {list(p.payload.keys()) if p.payload else 'None'}")

        return [self._point_to_result(point) for point in response.points]

    def _point_to_result(self, point: ScoredPoint) -> SearchResult:
        """Convert Qdrant ScoredPoint to SearchResult.

        Handles both standard format and LlamaIndex format (_node_content).
        """
        payload = point.payload or {}

        # Try to get content from different formats
        content = ""
        if "content" in payload:
            content = str(payload["content"])
        elif "_node_content" in payload:
            # LlamaIndex format - parse JSON to get text
            try:
                node_data = json.loads(payload["_node_content"])
                content = node_data.get("text", "")
            except (json.JSONDecodeError, TypeError):
                content = str(payload["_node_content"])
        elif "text" in payload:
            content = str(payload["text"])

        # Get source from different formats
        source = payload.get("source", payload.get("source_file", payload.get("file_name", "unknown")))

        return SearchResult(
            content=content,
            score=point.score,
            source=str(source),
            metadata={
                k: v
                for k, v in payload.items()
                if k not in ("content", "source", "_node_content", "text")
                and isinstance(v, (str, int, float, bool))
            },
        )

    async def health_check(self) -> bool:
        """Check if Qdrant is healthy.

        Returns:
            True if Qdrant is accessible.
        """
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False
