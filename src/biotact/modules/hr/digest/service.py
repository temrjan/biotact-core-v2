"""HR Digest service - business logic layer."""

import logging
from datetime import date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import Settings, get_settings
from biotact.modules.hr.digest.schemas import Digest, DigestCreate, DigestResponse
from biotact.modules.hr.digest.scraper import scrape_all_sources
from biotact.modules.hr.digest.summarizer import DigestSummarizer

logger = logging.getLogger(__name__)


class DigestService:
    """Service for managing HR News Digests."""

    def __init__(self, settings: Settings | None = None):
        """Initialize digest service.

        Args:
            settings: Application settings (uses get_settings() if None).
        """
        self.settings = settings or get_settings()

    async def generate_digest(
        self, hours: int = 24, generated_by: str = "auto"
    ) -> Digest:
        """Generate new digest from fresh news.

        Args:
            hours: How many hours back to scrape.
            generated_by: Who/what generated this digest.

        Returns:
            Generated digest object.
        """
        logger.info(f"Generating digest for last {hours} hours...")

        # Step 1: Scrape all sources
        news_items = await scrape_all_sources(self.settings, hours=hours)

        if not news_items:
            logger.warning("No news items found")
            return Digest(date=datetime.now(), sections=[])

        logger.info(f"Scraped {len(news_items)} news items")

        # Step 2: Summarize and categorize
        summarizer = DigestSummarizer(self.settings)
        digest = await summarizer.summarize(news_items)

        logger.info(
            f"Digest generated: {len(digest.sections)} sections, {digest.news_count} items"
        )

        return digest

    async def save_digest(
        self, digest: Digest, db: AsyncSession, generated_by: str = "auto"
    ) -> int:
        """Save digest to database.

        Args:
            digest: Digest object to save.
            db: Database session.
            generated_by: Generator identifier.

        Returns:
            ID of saved digest.
        """
        from biotact.models import HRDigest  # Import here to avoid circular deps

        digest_data = DigestCreate(
            date=digest.date,
            content_markdown=digest.to_markdown(),
            content_json=digest.model_dump(mode="json"),
            news_count=digest.news_count,
            generated_by=generated_by,
        )

        db_digest = HRDigest(**digest_data.model_dump())
        db.add(db_digest)
        await db.commit()
        await db.refresh(db_digest)

        logger.info(f"Digest saved to database: ID={db_digest.id}")

        return db_digest.id

    async def get_latest_digest(self, db: AsyncSession) -> DigestResponse | None:
        """Get latest digest from database.

        Args:
            db: Database session.

        Returns:
            Latest digest or None if no digests exist.
        """
        from biotact.models import HRDigest

        result = await db.execute(
            select(HRDigest).order_by(HRDigest.date.desc()).limit(1)
        )
        digest = result.scalar_one_or_none()

        if digest:
            return DigestResponse.model_validate(digest)

        return None

    async def get_digest_by_date(
        self, target_date: date, db: AsyncSession
    ) -> DigestResponse | None:
        """Get digest for specific date.

        Args:
            target_date: Date to fetch digest for.
            db: Database session.

        Returns:
            Digest for that date or None.
        """
        from biotact.models import HRDigest

        result = await db.execute(
            select(HRDigest).where(HRDigest.date == target_date)
        )
        digest = result.scalar_one_or_none()

        if digest:
            return DigestResponse.model_validate(digest)

        return None

    async def get_digest_history(
        self, limit: int = 10, offset: int = 0, db: AsyncSession | None = None
    ) -> list[DigestResponse]:
        """Get digest history.

        Args:
            limit: Maximum number of digests to return.
            offset: Number of digests to skip.
            db: Database session.

        Returns:
            List of digests, most recent first.
        """
        from biotact.models import HRDigest

        result = await db.execute(
            select(HRDigest)
            .order_by(HRDigest.date.desc())
            .limit(limit)
            .offset(offset)
        )
        digests = result.scalars().all()

        return [DigestResponse.model_validate(d) for d in digests]

    async def generate_and_save(
        self, db: AsyncSession, hours: int = 24, generated_by: str = "auto"
    ) -> DigestResponse:
        """Generate digest and save to database in one operation.

        Args:
            db: Database session.
            hours: Hours to look back.
            generated_by: Generator identifier.

        Returns:
            Saved digest response.
        """
        digest = await self.generate_digest(hours=hours, generated_by=generated_by)

        # Check if digest already exists for this date (avoid UniqueViolation)
        target_date = digest.date.date()
        existing = await self.get_digest_by_date(target_date, db)
        if existing:
            logger.info(f"Digest for {target_date} already exists (id={existing.id}), updating")
            await self._update_digest(existing.id, digest, db, generated_by)
        else:
            await self.save_digest(digest, db, generated_by=generated_by)

        saved = await self.get_digest_by_date(target_date, db)
        if not saved:
            raise RuntimeError("Failed to retrieve saved digest")

        return saved
    async def _update_digest(
        self, digest_id: int, digest: Digest, db: AsyncSession, generated_by: str = "auto"
    ) -> None:
        """Update existing digest in database.

        Args:
            digest_id: ID of existing digest to update.
            digest: New digest data.
            db: Database session.
            generated_by: Generator identifier.
        """
        from sqlalchemy import update as sa_update
        from biotact.models import HRDigest

        await db.execute(
            sa_update(HRDigest)
            .where(HRDigest.id == digest_id)
            .values(
                content_markdown=digest.to_markdown(),
                content_json=digest.model_dump(mode="json"),
                news_count=digest.news_count,
                generated_by=generated_by,
            )
        )
        await db.commit()
        logger.info(f"Digest {digest_id} updated successfully")

    async def cleanup_old_digests(
        self,
        db: AsyncSession,
        retention_days: int = 7,
    ) -> int:
        """Delete digests older than retention_days.

        News items will be automatically deleted via CASCADE.

        Args:
            db: Database session.
            retention_days: Number of days to keep digests.

        Returns:
            Number of digests deleted.
        """
        from datetime import timedelta
        from biotact.models import HRDigest

        cutoff_date = datetime.now().date() - timedelta(days=retention_days)

        logger.info(f"Cleaning up digests older than {cutoff_date} (retention: {retention_days} days)")

        # Count before deletion
        count_result = await db.execute(
            select(func.count(HRDigest.id)).where(HRDigest.date < cutoff_date)
        )
        count_before = count_result.scalar() or 0

        if count_before == 0:
            logger.info("No old digests to clean up")
            return 0

        # Delete old digests (news_items will be deleted via CASCADE)
        result = await db.execute(
            delete(HRDigest).where(HRDigest.date < cutoff_date)
        )
        await db.commit()

        deleted_count = result.rowcount
        logger.info(f"Cleaned up {deleted_count} old digests and their news items")

        return deleted_count



# Singleton instance
digest_service = DigestService()
