"""Shared utilities for the media module.

Note: ``translate_to_english`` duplicates logic from
``biotact.api.v1.knowledge``. Extract to ``services/rag/utils.py`` as a
follow-up (outside Этап 3 scope to keep the change focused).
"""

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

TRANSLATE_MODEL = "gpt-4.1-nano"
TRANSLATE_MAX_TOKENS = 200


async def translate_to_english(client: AsyncOpenAI, text: str) -> str:
    """Translate a query to English if it looks non-ASCII; otherwise return as-is."""
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii < len(text) * 0.3:
        return text

    try:
        response = await client.chat.completions.create(
            model=TRANSLATE_MODEL,
            max_completion_tokens=TRANSLATE_MAX_TOKENS,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Translate the following search query to English. "
                        "Return ONLY the translation, nothing else."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
    except Exception:
        logger.warning("Translation failed, using original query")
        return text

    translated = (response.choices[0].message.content or text).strip()
    return translated or text
