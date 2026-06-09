"""HR Chat focused data extraction via LLM."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT_TEMPLATE = (
    "Извлеки данные из текста переписки и верни JSON.\n"
    "Поля: {fields}\n\n"
    "Правила:\n"
    "- FIO: ЗАГЛАВНЫМИ кириллицей (ПЕТРОВ АЛЕКСЕЙ СЕРГЕЕВИЧ)\n"
    "- FIO_LATIN: ЗАГЛАВНЫМИ латиницей (PETROV ALEKSEY SERGEEVICH)\n"
    "- FIO_SHORT_LATIN: PETROV A. S.\n"
    "- CONTRACT_TYPE: 'неопределённый срок' или 'определённый срок'\n"
    "- CONTRACT_TYPE_UZ: 'муддатсиз' или 'муайян муддатга'\n"
    "- WORK_TYPE: 'основной работы' или 'работы по совместительству'\n"
    "- WORK_TYPE_UZ: 'асосий иш жойи' или 'ўриндошлик бўйича иш жойи'\n"
    "- Даты: ДД.ММ.ГГГГ\n"
    "- Если поле нельзя извлечь — пустая строка\n\n"
    "Верни ТОЛЬКО JSON, без пояснений.\n\n"
    "Переписка:\n{context}"
)


async def extract_data_from_context(
    openai: AsyncOpenAI,
    model: str,
    context: str,
    fields: list[str],
) -> dict[str, str]:
    """Use a focused LLM call to extract structured data from conversation."""
    prompt = _EXTRACTION_PROMPT_TEMPLATE.format(
        fields=json.dumps(fields),
        context=context,
    )
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
    except Exception:
        logger.exception("Failed to extract data from context")
        return {}
