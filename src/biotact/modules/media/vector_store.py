"""Qdrant vector store for media transcription chunks.

Separate collection: media_transcriptions (3072 dims, Cosine).
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

COLLECTION_NAME = "media_transcriptions"
VECTOR_SIZE = 3072  # text-embedding-3-large


class MediaTranscriptionVectorStore:
    """Qdrant operations for transcription chunks (full-text RAG)."""

    def __init__(self, settings: Settings) -> None:
        self.client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )

    async def ensure_collection(self) -> None:
        """Create media_transcriptions collection if it doesn't exist."""
        exists = await self.client.collection_exists(COLLECTION_NAME)
        if not exists:
            await self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection: %s", COLLECTION_NAME)

    async def upsert_chunks(
        self,
        transcription_id: str,
        user_id: int,
        created_at: str,
        original_filename: str,
        title: str,
        summary: str,
        keywords: list[str],
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> int:
        """Upsert transcript chunks into Qdrant.

        Args:
            transcription_id: UUID of the MediaTranscription row.
            user_id: Author (MediaTranscription.uploaded_by).
            created_at: ISO-formatted creation timestamp.
            original_filename: Original audio filename.
            title: LLM-generated title.
            summary: LLM-generated 1-2 sentence summary.
            keywords: LLM-extracted keywords.
            chunks: Text chunks to upsert.
            embeddings: Corresponding embedding vectors.

        Returns:
            Number of points upserted.
        """
        if not chunks:
            return 0

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "transcription_id": transcription_id,
                    "user_id": user_id,
                    "created_at": created_at,
                    "original_filename": original_filename,
                    "title": title,
                    "summary": summary,
                    "keywords": keywords,
                    "chunk_index": i,
                    "content": chunk,
                },
            )
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]

        await self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
        )
        logger.info(
            "Upserted %d chunks for transcription %s", len(points), transcription_id
        )
        return len(points)

    async def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        score_threshold: float = 0.3,
    ) -> list[dict[str, object]]:
        """Search transcription chunks by vector similarity.

        Returns list of dicts with content, score, and payload metadata.
        """
        response = await self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold,
        )
        return [self._point_to_dict(point) for point in response.points]

    async def delete_transcription_vectors(self, transcription_id: str) -> None:
        """Remove all chunks for a specific transcription."""
        await self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="transcription_id",
                        match=MatchValue(value=transcription_id),
                    )
                ]
            ),
        )
        logger.info("Deleted vectors for transcription %s", transcription_id)

    @staticmethod
    def _point_to_dict(point: ScoredPoint) -> dict[str, object]:
        payload = point.payload or {}
        return {
            "content": str(payload.get("content", "")),
            "transcription_id": str(payload.get("transcription_id", "")),
            "title": str(payload.get("title", "")),
            "summary": str(payload.get("summary", "")),
            "keywords": payload.get("keywords", []),
            "original_filename": str(payload.get("original_filename", "")),
            "created_at": str(payload.get("created_at", "")),
            "chunk_index": int(payload.get("chunk_index", 0)),
            "score": point.score,
        }
