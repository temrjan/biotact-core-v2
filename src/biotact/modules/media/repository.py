"""Repository for media transcription persistence."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.modules.media.models import MediaTranscription


class MediaTranscriptionRepository:
    """CRUD for MediaTranscription."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        original_filename: str,
        title: str,
        text: str,
        uploaded_by: int,
    ) -> MediaTranscription:
        """Insert a new transcription record."""
        record = MediaTranscription(
            original_filename=original_filename,
            title=title,
            text=text,
            uploaded_by=uploaded_by,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record, ["creator"])
        return record

    async def get_by_uuid(self, transcription_id: str) -> MediaTranscription | None:
        """Fetch transcription by external UUID."""
        result = await self.session.execute(
            select(MediaTranscription).where(
                MediaTranscription.transcription_id == transcription_id
            )
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        limit: int,
        offset: int,
    ) -> tuple[list[MediaTranscription], int]:
        """Return (items, total) — items sorted by created_at desc."""
        items_q = (
            select(MediaTranscription)
            .order_by(MediaTranscription.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        total_q = select(func.count(MediaTranscription.id))

        items_r = await self.session.execute(items_q)
        total_r = await self.session.execute(total_q)

        return list(items_r.scalars().all()), total_r.scalar_one()

    async def update_enrichment(
        self,
        record: MediaTranscription,
        title: str,
        summary: str,
        keywords: list[str],
        chunk_count: int,
    ) -> MediaTranscription:
        """Persist enrichment results after indexing completes."""
        record.title = title
        record.summary = summary
        record.keywords = keywords
        record.is_indexed = True
        record.chunk_count = chunk_count
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def delete(self, record: MediaTranscription) -> None:
        """Delete a transcription record."""
        await self.session.delete(record)
        await self.session.flush()
