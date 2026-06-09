"""HR document retention policy — hard-delete transient documents older than 30 days.

Business decision (CEO, 2026-06-09): all categories are transient.
STATUTORY_CATEGORIES is empty; every generated document is deleted after 30 days.
Important originals are kept by the director locally.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from biotact.modules.hr.library.models import HRDocument, HRTemplate

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Business-confirmed list — empty means *everything* is transient.
STATUTORY_CATEGORIES: frozenset[str] = frozenset()

DEFAULT_RETENTION_DAYS = 30


async def cleanup_old_documents(
    db: AsyncSession,
    now: datetime,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> int:
    """Delete HR documents older than retention_days.

    Skips documents whose template category is in STATUTORY_CATEGORIES.
    Because the current statutory set is empty, *all* old documents are
    eligible for deletion.

    Args:
        db: Database session.
        now: Injectable clock for deterministic testing.
        retention_days: Cutoff age in days.

    Returns:
        Number of deleted documents (files + DB rows).
    """
    cutoff = now - timedelta(days=retention_days)

    stmt = (
        select(HRDocument, HRTemplate.category)
        .outerjoin(HRTemplate, HRDocument.template_id == HRTemplate.id)
        .where(HRDocument.created_at < cutoff)
    )
    result = await db.execute(stmt)
    rows = result.all()

    deleted_count = 0
    for doc, category in rows:
        if category in STATUTORY_CATEGORIES:
            continue

        logger.warning(
            "Deleting old document id=%d file_id=%s path=%s category=%s",
            doc.id,
            doc.file_id,
            doc.file_path,
            category or "null",
        )

        try:
            Path(doc.file_path).unlink(missing_ok=True)
        except OSError as exc:
            logger.error(
                "Failed to unlink document id=%d path=%s: %s",
                doc.id,
                doc.file_path,
                exc,
            )

        await db.delete(doc)
        deleted_count += 1

    return deleted_count


async def run_retention_cleanup(
    now: datetime | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> None:
    """Entry-point for APScheduler job.

    Creates its own DB session, commits on success, rolls back on error.
    """
    from biotact.core.database import AsyncSessionLocal

    if now is None:
        now = datetime.now(UTC)

    async with AsyncSessionLocal() as db, db.begin():
        deleted = await cleanup_old_documents(
            db, now, retention_days=retention_days
        )
        if deleted:
            logger.info("Retention cleanup finished: %d document(s) deleted", deleted)
        else:
            logger.info("Retention cleanup finished: nothing to delete")


def setup_hr_retention_scheduler(scheduler: AsyncIOScheduler) -> None:
    """Wire the daily retention job into APScheduler.

    Args:
        scheduler: APScheduler instance from main.py lifespan.
    """
    scheduler.add_job(
        run_retention_cleanup,
        trigger="cron",
        hour=3,
        minute=0,
        id="hr_retention_cleanup",
        replace_existing=True,
        timezone="UTC",
        misfire_grace_time=3600,
    )
    logger.info("HR retention scheduler configured: daily at 03:00 UTC")
