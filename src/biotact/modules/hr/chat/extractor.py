"""HR Chat focused data extraction via LLM."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from openai import OpenAIError

from biotact.modules.hr.chat.field_rules import build_extractor_rules

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


def _build_extraction_prompt(fields: list[str], category: str, context: str) -> str:
    """Assemble the focused-extraction prompt with per-category field rules.

    Uses an f-string (not ``str.format``) so ``{`` / ``}`` in the user's text
    are never interpreted as format placeholders.
    """
    return (
        "Извлеки данные из текста переписки и верни JSON.\n"
        f"Поля: {json.dumps(fields)}\n\n"
        f"{build_extractor_rules(category)}\n\n"
        "Правила извлечения:\n"
        "- Если поле нельзя извлечь — пустая строка\n\n"
        "Верни ТОЛЬКО JSON, без пояснений.\n\n"
        f"Переписка:\n{context}"
    )


async def extract_data_from_context(
    openai: AsyncOpenAI,
    model: str,
    context: str,
    fields: list[str],
    category: str,
) -> dict[str, str]:
    """Use a focused LLM call to extract structured data from conversation.

    ``category`` selects the per-category field rules (the same single source
    as the system prompt) so the fallback path knows document-specific fields
    like ``GPD_NUMBER`` / ``GPD_DATE`` instead of guessing from bare names.
    """
    prompt = _build_extraction_prompt(fields, category, context)
    try:
        response = await openai.chat.completions.create(
            model=model,
            max_completion_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        logger.info("Extracted %d fields from context", len(data))
        return {k: str(v) for k, v in data.items() if v}
    except (OpenAIError, json.JSONDecodeError):
        logger.exception("Failed to extract data from context")
        return {}
