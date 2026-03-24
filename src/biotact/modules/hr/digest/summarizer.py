"""AI-powered news summarizer and categorizer."""

import json
import logging
import re
from datetime import datetime

from openai import AsyncOpenAI

from biotact.core.config import Settings
from biotact.modules.hr.digest.config import DIGEST_SYSTEM_PROMPT
from biotact.modules.hr.digest.schemas import (
    Digest,
    DigestItem,
    DigestSection,
    NewsItem,
)

logger = logging.getLogger(__name__)


class DigestSummarizer:
    """Summarize and categorize news using OpenAI (gpt-4o-mini)."""

    def __init__(self, settings: Settings):
        """Initialize summarizer with direct OpenAI client.

        Args:
            settings: Application settings.
        """
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o-mini"
        self._source_items: dict[str, NewsItem] = {}

    async def summarize(self, news_items: list[NewsItem]) -> Digest:
        """Create digest from news items.

        Args:
            news_items: List of raw news items from scrapers.

        Returns:
            Structured digest with categorized summaries.
        """
        if not news_items:
            logger.warning("No news items to summarize")
            return Digest(date=datetime.now(), sections=[])

        logger.info(f"Summarizing {len(news_items)} news items")

        # Save items for source matching later
        for item in news_items:
            self._source_items[item.source] = item

        # Prepare news for LLM
        news_list = []
        for i, item in enumerate(news_items, 1):
            news_list.append(
                f"{i}. [{item.source}] {item.title or ''}\n{item.content[:500]}"
            )

        news_text = "\n\n".join(news_list)

        # Create prompt
        prompt = f"""Проанализируй следующие новости и создай структурированный HR дайджест.

НОВОСТИ:
{news_text}

Верни ответ СТРОГО в JSON формате (без markdown кода):
{{
  "categories": [
    {{
      "category": "Законодательство",
      "emoji": "📋",
      "items": [
        {{
          "source": "lex.uz",
          "text": "Краткое резюме новости (1-2 предложения)"
        }}
      ]
    }}
  ]
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": DIGEST_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.3,
            )

            response_text = response.choices[0].message.content or ""

            # Parse response
            digest = self._parse_response(response_text, news_items)
            logger.info(
                f"Digest created: {len(digest.sections)} categories, {digest.news_count} items"
            )

            return digest

        except Exception as e:
            logger.error(f"Error summarizing: {e}")
            return self._create_fallback_digest(news_items)

    def _parse_response(self, response: str, news_items: list[NewsItem]) -> Digest:  # noqa: ARG002
        """Parse LLM JSON response into Digest."""
        response = response.strip()
        if response.startswith("```"):
            match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
            if match:
                response = match.group(1)

        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Response: {response}")
            raise

        sections = []
        for cat_data in data.get("categories", []):
            items = []
            for item_data in cat_data.get("items", []):
                source = item_data.get("source", "")
                text = item_data.get("text", "")
                url = self._find_url_for_source(source)
                items.append(DigestItem(source=source, text=text, url=url))

            sections.append(
                DigestSection(
                    category=cat_data.get("category", "Прочее"),
                    emoji=cat_data.get("emoji", "📌"),
                    items=items,
                )
            )

        return Digest(date=datetime.now(), sections=sections)

    def _find_url_for_source(self, source: str) -> str | None:
        """Find URL for given source name."""
        if source in self._source_items:
            return self._source_items[source].url

        for src_name, item in self._source_items.items():
            if source.lower() in src_name.lower() or src_name.lower() in source.lower():
                return item.url

        return None

    def _create_fallback_digest(self, news_items: list[NewsItem]) -> Digest:
        """Create simple digest without AI categorization."""
        logger.warning("Creating fallback digest (no AI categorization)")

        items = [
            DigestItem(
                source=item.source, text=item.content[:200] + "...", url=item.url
            )
            for item in news_items
        ]

        section = DigestSection(category="Все новости", emoji="📰", items=items)

        return Digest(date=datetime.now(), sections=[section])
