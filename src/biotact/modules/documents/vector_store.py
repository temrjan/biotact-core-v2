"""Qdrant vector store for user-uploaded documents.

Separate from the main knowledge-evolution collection.
Collection: user_files (3072 dims, Cosine).
"""

import logging
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from biotact.core.config import Settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "user_files"
VECTOR_SIZE = 3072  # text-embedding-3-large


class FileVectorStore:
    """Qdrant operations for user-uploaded file chunks."""

    def __init__(self, settings: Settings) -> None:
        self.client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )

    async def ensure_collection(self) -> None:
        """Create user_files collection if it doesn't exist."""
        exists = await self.client.collection_exists(COLLECTION_NAME)
        if not exists:
            await self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")

    async def upsert_chunks(
        self,
        file_id: str,
        file_name: str,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> int:
        """Upsert file chunks into Qdrant.

        Args:
            file_id: UUID of the file.
            file_name: Display name for sources.
            chunks: List of text chunks.
            embeddings: Corresponding embeddings.

        Returns:
            Number of points upserted.
        """
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "file_id": file_id,
                    "file_name": file_name,
                    "chunk_index": i,
                    "content": chunk,
                },
            )
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]

        if points:
            await self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
            )

        logger.info(f"Upserted {len(points)} chunks for file {file_name}")
        return len(points)

    async def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        score_threshold: float = 0.3,
    ) -> list[dict[str, str | float]]:
        """Search across all user files (shared platform — no user filter).

        Args:
            query_vector: Query embedding.
            limit: Max results.
            score_threshold: Min similarity.

        Returns:
            List of dicts with content, file_name, file_id, score.
        """
        response = await self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold,
        )

        return [self._point_to_dict(point) for point in response.points]

    async def delete_file_vectors(self, file_id: str) -> None:
        """Delete all vectors for a specific file.

        Args:
            file_id: UUID of the file to remove.
        """
        await self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="file_id",
                        match=MatchValue(value=file_id),
                    )
                ]
            ),
        )
        logger.info(f"Deleted vectors for file {file_id}")

    async def delete_files_vectors(self, file_ids: list[str]) -> None:
        """Delete vectors for multiple files (batch, for folder deletion).

        Args:
            file_ids: List of file UUIDs.
        """
        for fid in file_ids:
            await self.delete_file_vectors(fid)

    def _point_to_dict(self, point: ScoredPoint) -> dict[str, str | float]:
        """Convert ScoredPoint to simple dict."""
        payload = point.payload or {}
        return {
            "content": str(payload.get("content", "")),
            "file_name": str(payload.get("file_name", "unknown")),
            "file_id": str(payload.get("file_id", "")),
            "chunk_index": int(payload.get("chunk_index", 0)),
            "score": point.score,
        }
