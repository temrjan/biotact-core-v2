"""Content scraper for web sources and Telegram channels."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from telethon import TelegramClient

from biotact.core.config import Settings
from biotact.modules.hr.digest.config import TELEGRAM_CHANNELS, WEB_SOURCES
from biotact.modules.hr.digest.schemas import NewsItem

logger = logging.getLogger(__name__)


class WebScraper:
    """Scraper for web sources using Firecrawl API."""

    def __init__(self, settings: Settings):
        """Initialize web scraper.

        Args:
            settings: Application settings with Firecrawl API key.
        """
        self.api_key = settings.firecrawl_api_key
        self.api_url = "https://api.firecrawl.dev/v1/scrape"

    async def scrape_url(
        self,
        client: httpx.AsyncClient,
        name: str,
        url: str,
    ) -> NewsItem | None:
        """Scrape single URL using Firecrawl.

        Args:
            client: HTTP client instance.
            name: Source name.
            url: URL to scrape.

        Returns:
            NewsItem if successful, None otherwise.
        """
        try:
            logger.info(f"Scraping {name}: {url}")

            resp = await client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "url": url,
                    "formats": ["markdown"],
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            if not data.get("success"):
                logger.warning(f"Firecrawl failed for {name}: {data.get('error')}")
                return None

            markdown = data.get("data", {}).get("markdown", "")
            if not markdown:
                logger.warning(f"No markdown content from {name}")
                return None

            return NewsItem(
                source=name,
                title=None,
                content=markdown[:5000],  # Limit content size
                url=url,
                published_at=datetime.now(timezone.utc),
            )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error scraping {name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error scraping {name}: {e}")
            return None

    async def scrape_all(self) -> list[NewsItem]:
        """Scrape all web sources concurrently.

        Returns:
            List of successfully scraped NewsItems.
        """
        async with httpx.AsyncClient() as client:
            tasks = [self.scrape_url(client, name, url) for name, url in WEB_SOURCES]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        items = [r for r in results if isinstance(r, NewsItem)]
        logger.info(f"Scraped {len(items)}/{len(WEB_SOURCES)} web sources")

        return items


class TelegramScraper:
    """Scraper for Telegram channels using Telethon."""

    def __init__(self, settings: Settings):
        """Initialize Telegram scraper.

        Args:
            settings: Application settings with Telegram credentials.
        """
        self.api_id = settings.telegram_api_id
        self.api_hash = settings.telegram_api_hash.get_secret_value()
        self.phone = settings.telegram_phone
        self.session_dir = Path("/app/.sessions")  # Docker path
        self.session_dir.mkdir(parents=True, exist_ok=True)

    async def scrape_channel(
        self,
        client: TelegramClient,
        channel: str,
        hours: int = 24,
    ) -> list[NewsItem]:
        """Scrape messages from Telegram channel.

        Args:
            client: Telethon client instance.
            channel: Channel username (e.g., @bhblaw).
            hours: Number of hours to look back.

        Returns:
            List of NewsItems from channel.
        """
        items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        try:
            logger.info(f"Scraping Telegram channel: {channel}")

            async for message in client.iter_messages(channel, limit=50):
                if message.date < cutoff:
                    break

                if not message.text:
                    continue

                # Build URL to specific message
                channel_name = channel.lstrip("@")
                msg_url = f"https://t.me/{channel_name}/{message.id}"

                items.append(
                    NewsItem(
                        source=channel,
                        title=None,
                        content=message.text[:2000],  # Limit content
                        url=msg_url,
                        published_at=message.date,
                    )
                )

            logger.info(f"Found {len(items)} messages from {channel}")

        except Exception as e:
            logger.error(f"Error scraping {channel}: {e}")

        return items

    async def scrape_all(self, hours: int = 24) -> list[NewsItem]:
        """Scrape all Telegram channels.

        Args:
            hours: Number of hours to look back.

        Returns:
            List of NewsItems from all channels.
        """
        session_path = self.session_dir / "telegram.session"
        client = TelegramClient(str(session_path), self.api_id, self.api_hash)

        try:
            await client.connect()

            if not await client.is_user_authorized():
                logger.warning("Telegram client not authorized - skipping")
                return []

            tasks = [
                self.scrape_channel(client, channel, hours)
                for channel in TELEGRAM_CHANNELS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            items = []
            for r in results:
                if isinstance(r, list):
                    items.extend(r)

            logger.info(
                f"Scraped {len(items)} items from {len(TELEGRAM_CHANNELS)} Telegram channels"
            )

            return items

        finally:
            await client.disconnect()


async def scrape_all_sources(settings: Settings, hours: int = 24) -> list[NewsItem]:
    """Scrape all sources (web + Telegram).

    Args:
        settings: Application settings.
        hours: Number of hours to look back for Telegram.

    Returns:
        Combined list of NewsItems from all sources.
    """
    web_scraper = WebScraper(settings)
    telegram_scraper = TelegramScraper(settings)

    # Run scrapers concurrently
    web_items, telegram_items = await asyncio.gather(
        web_scraper.scrape_all(),
        telegram_scraper.scrape_all(hours),
        return_exceptions=True,
    )

    all_items = []
    if isinstance(web_items, list):
        all_items.extend(web_items)
    if isinstance(telegram_items, list):
        all_items.extend(telegram_items)

    logger.info(f"Total scraped: {len(all_items)} items from all sources")

    return all_items
