"""Transcription indexing pipeline: enrich → chunk → embed → upsert."""

import asyncio
import logging
from datetime import datetime

from openai import AsyncOpenAI

from biotact.modules.documents.indexing_service import chunk_text
from biotact.modules.media.enrich_service import EnrichResult, enrich_transcript
from biotact.modules.media.vector_store import MediaTranscriptionVectorStore
from biotact.services.rag.embedding import EmbeddingService

logger = logging.getLogger(__name__)

# Guard against concurrent indexing to protect RAM.
_indexing_semaphore = asyncio.Semaphore(1)

CHUNK_SIZE = 2000  # characters (~500 tokens for Russian)
CHUNK_OVERLAP = 400  # ~20% overlap (~100 tokens)
EMBED_BATCH_SIZE = 100


async def index_transcription(
    transcription_id: str,
    user_id: int,
    created_at: datetime,
    original_filename: str,
    text: str,
    llm_client: AsyncOpenAI,
    llm_model: str,
    embedding_service: EmbeddingService,
    vector_store: MediaTranscriptionVectorStore,
) -> tuple[EnrichResult, int]:
    """Run the full indexing pipeline for a single transcription.

    Args:
        transcription_id: External UUID of the record.
        user_id: Author id (users.id).
        created_at: Creation timestamp from DB.
        original_filename: Original audio filename.
        text: Full transcribed text.
        llm_client: OpenAI client for enrichment.
        llm_model: Chat model name (e.g. gpt-4o-mini).
        embedding_service: Pre-built EmbeddingService.
        vector_store: Media transcription vector store.

    Returns:
        Tuple of (EnrichResult, chunk_count). EnrichResult may be empty
        on LLM failure; the caller should apply a fallback title.
    """
    async with _indexing_semaphore:
        logger.info("Indexing transcription %s (len=%d)", transcription_id, len(text))

        enrich = await enrich_transcript(llm_client, llm_model, text)

        chunks = chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        if not chunks:
            logger.warning("No chunks produced for %s", transcription_id)
            return enrich, 0

        embeddings: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i : i + EMBED_BATCH_SIZE]
            embeddings.extend(await embedding_service.embed_texts(batch))

        chunk_count = await vector_store.upsert_chunks(
            transcription_id=transcription_id,
            user_id=user_id,
            created_at=created_at.isoformat(),
            original_filename=original_filename,
            title=enrich.title,
            summary=enrich.summary,
            keywords=enrich.keywords,
            chunks=chunks,
            embeddings=embeddings,
        )

        logger.info(
            "Indexed transcription %s: %d chunks", transcription_id, chunk_count
        )
        return enrich, chunk_count
