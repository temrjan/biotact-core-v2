"""HR Chat document generation — render DOCX and persist to DB."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from biotact.modules.hr.chat.categories import postprocess
from biotact.modules.hr.chat.extractor import extract_data_from_context
from biotact.modules.hr.documents.renderer import render_template
from biotact.modules.hr.library.models import HRDocument, HRTemplate

if TYPE_CHECKING:
    from datetime import datetime

    from openai import AsyncOpenAI
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

RENDER_DIR = Path("data/hr_rendered")


async def generate_hr_document(
    db: AsyncSession,
    args: dict[str, Any],
    *,
    openai: AsyncOpenAI,
    model: str,
    user_id: int,
    messages_context: str,
    now: datetime,
) -> str:
    """Render a DOCX from AI-provided data and persist it.

    Returns a public download URL or an error message.
    """
    template_id = args.get("template_id")
    data = args.get("data", {})

    if not template_id:
        return "Ошибка: не указан template_id"

    result = await db.execute(select(HRTemplate).where(HRTemplate.id == template_id))
    db_template = result.scalar_one_or_none()
    if not db_template:
        return "Ошибка: шаблон не найден"

    fields = db_template.template_fields or []
    missing = [f for f in fields if f not in data or not data[f]]
    if missing and messages_context:
        logger.info(
            "generate_document: %d/%d fields missing, extracting via LLM",
            len(missing),
            len(fields),
        )
        extracted = await extract_data_from_context(
            openai, model, messages_context, fields
        )
        for k, v in extracted.items():
            if k not in data or not data.get(k):
                data[k] = v

    data = postprocess(data, category=db_template.category, now=now)

    try:
        RENDER_DIR.mkdir(parents=True, exist_ok=True)
        file_id = uuid.uuid4().hex[:12]
        out_path = RENDER_DIR / f"{file_id}.docx"

        buffer = render_template(db_template.file_path, data)
        rendered_bytes = buffer.read()
        out_path.write_bytes(rendered_bytes)

        employee = data.get("FIO") or data.get("FIO_LATIN") or "—"
        hr_doc = HRDocument(
            file_id=file_id,
            template_id=db_template.id,
            template_name=db_template.name,
            employee_name=employee,
            file_path=str(out_path),
            file_size=len(rendered_bytes),
            created_by=user_id,
        )
        db.add(hr_doc)
        await db.flush()

        logger.info(
            "Document rendered: %s employee=%s fields=%d",
            out_path,
            employee,
            len(data),
        )
        return f"/api/v1/hr/documents/download/{file_id}"
    except Exception as e:
        logger.exception("Render failed for template %d", template_id)
        return f"Ошибка рендеринга: {e}"
