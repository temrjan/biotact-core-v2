"""APScheduler setup for automatic digest generation."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


async def generate_daily_digest() -> None:
    """Job function for generating daily digest.

    This function is called by APScheduler every day at 08:00.
    """
    from aiogram import Bot

    from biotact.core.config import get_settings
    from biotact.core.database import AsyncSessionLocal
    from biotact.modules.news_digest.service import digest_service

    logger.info("🤖 Starting automatic daily digest generation...")

    settings = get_settings()

    try:
        # Generate digest
        async with AsyncSessionLocal() as db:
            digest_response = await digest_service.generate_and_save(
                db=db, hours=24, generated_by="auto"
            )

        logger.info(f"✅ Digest generated: {digest_response.news_count} items")

        # Send to Telegram
        bot = Bot(token=settings.hr_digest_bot_token.get_secret_value())

        try:
            await bot.send_message(
                chat_id=settings.hr_digest_chat_id,
                text=digest_response.content_markdown,
                parse_mode="Markdown",
            )
            logger.info("📤 Digest sent to Telegram")

        except Exception as e:
            logger.error(f"Failed to send digest to Telegram: {e}")

        finally:
            await bot.session.close()

    except Exception as e:
        logger.error(f"❌ Failed to generate digest: {e}", exc_info=True)


def setup_digest_scheduler(scheduler: AsyncIOScheduler) -> None:
    """Setup digest scheduler with daily job.

    Args:
        scheduler: APScheduler instance from main.py.
    """
    # Run every day at 08:00 Tashkent time
    scheduler.add_job(
        generate_daily_digest,
        trigger="cron",
        hour=8,
        minute=0,
        id="hr_digest_daily",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow 1 hour grace period
    )

    # Run cleanup every day at 00:00 Tashkent time
    scheduler.add_job(
        cleanup_old_data,
        trigger="cron",
        hour=0,
        minute=0,
        id="hr_digest_cleanup",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    logger.info("📅 HR Digest scheduler configured: daily at 08:00")


async def cleanup_old_data() -> None:
    """Job function for cleaning up old digests.

    This function is called by APScheduler every day at 00:00.
    Deletes digests older than DIGEST_RETENTION_DAYS (default 30).
    """
    from biotact.core.config import get_settings
    from biotact.core.database import AsyncSessionLocal
    from biotact.modules.news_digest.service import digest_service

    settings = get_settings()

    try:
        async with AsyncSessionLocal() as db:
            deleted_count = await digest_service.cleanup_old_digests(
                db=db, retention_days=settings.digest_retention_days
            )

            if deleted_count > 0:
                logger.info(f"🗑️ Cleanup completed: {deleted_count} old digests removed")
            else:
                logger.info("✅ Cleanup completed: no old digests to remove")

    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}", exc_info=True)
