"""LLM enrichment for transcripts: generate title, summary, keywords."""

import json
import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

ENRICH_SOURCE_MAX_CHARS = 12000  # truncate very long transcripts before LLM
TITLE_MAX_CHARS = 252
SUMMARY_MAX_CHARS = 500
KEYWORDS_MAX = 10

SYSTEM_PROMPT = """Ты ассистент, который извлекает метаданные из русского транскрипта речи.

Верни строго JSON-объект со следующими полями:
- "title": краткий заголовок темы (3-7 слов, без кавычек)
- "summary": одно-два предложения о главной теме (до 500 символов)
- "keywords": массив из 5-10 ключевых слов или именованных сущностей (на русском)

Никаких пояснений. Только валидный JSON."""


@dataclass
class EnrichResult:
    """Structured output of LLM enrichment pass."""

    title: str = ""
    summary: str = ""
    keywords: list[str] = field(default_factory=list)


async def enrich_transcript(
    client: AsyncOpenAI,
    model: str,
    text: str,
) -> EnrichResult:
    """Ask LLM for {title, summary, keywords}. Return empty result on failure.

    The caller is responsible for the final fallback (e.g. MVP title from
    the first sentence or creation date).
    """
    source = text.strip()
    if not source:
        return EnrichResult()

    truncated = source[:ENRICH_SOURCE_MAX_CHARS]

    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": truncated},
            ],
        )
    except Exception:
        logger.exception("Enrichment LLM call failed")
        return EnrichResult()

    raw = response.choices[0].message.content or ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Enrichment returned non-JSON output: %s", raw[:200])
        return EnrichResult()

    return _sanitize(data)


def _sanitize(data: object) -> EnrichResult:
    """Validate and trim LLM output into safe bounded values."""
    if not isinstance(data, dict):
        return EnrichResult()

    title = str(data.get("title") or "").strip()
    if len(title) > TITLE_MAX_CHARS:
        title = title[:TITLE_MAX_CHARS] + "…"

    summary = str(data.get("summary") or "").strip()
    if len(summary) > SUMMARY_MAX_CHARS:
        summary = summary[:SUMMARY_MAX_CHARS] + "…"

    raw_keywords = data.get("keywords") or []
    keywords: list[str] = []
    if isinstance(raw_keywords, list):
        for item in raw_keywords[:KEYWORDS_MAX]:
            keyword = str(item).strip()
            if keyword:
                keywords.append(keyword)

    return EnrichResult(title=title, summary=summary, keywords=keywords)
