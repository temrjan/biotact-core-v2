"""HR Chat document generation — render DOCX and persist to DB."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from biotact.core.config import get_settings
from biotact.modules.hr.chat.categories import postprocess
from biotact.modules.hr.chat.extractor import extract_data_from_context
from biotact.modules.hr.documents.renderer import render_template
from biotact.modules.hr.library.models import HRDocument, HRTemplate

if TYPE_CHECKING:
    from datetime import datetime

    from openai import AsyncOpenAI
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


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

    Fields still empty after post-processing block the render: docxtpl runs on a
    default Jinja environment, so an unfilled placeholder would silently become
    an empty string in a document the chat then reports as ready. The check runs
    *after* ``postprocess`` because most of a template's fields are derived
    (salary in words, weekly hours, dates) rather than supplied by HR.

    Returns a public download URL, or a message for the model — either what to
    ask the user for, or the reason the render failed.
    """
    template_id = args.get("template_id")
    data = args.get("data", {})

    if not template_id:
        return "Ошибка: не указан template_id"

    # ``is_active`` is part of the lookup, not a check afterwards: a category
    # keeps its superseded versions as rows, and rendering a contract from an
    # outdated legal wording is not something the caller may opt into. The two
    # cases are answered together because the model's recovery is the same —
    # ask the library for the current template and retry.
    result = await db.execute(
        select(HRTemplate)
        .where(HRTemplate.id == template_id)
        .where(HRTemplate.is_active.is_(True))
    )
    db_template = result.scalar_one_or_none()
    if not db_template:
        return (
            "Ошибка: шаблон не найден или больше не актуален. "
            "Возьми актуальный шаблон из списка доступных и повтори."
        )

    fields = db_template.template_fields or []
    missing = [f for f in fields if f not in data or not data[f]]
    if missing and messages_context:
        logger.info(
            "generate_document: %d/%d fields missing %s, extracting via LLM",
            len(missing),
            len(fields),
            missing,  # field NAMES (not values) — safe to log
        )
        extracted = await extract_data_from_context(
            openai, model, messages_context, fields, db_template.category
        )
        for k, v in extracted.items():
            if k not in data or not data.get(k):
                data[k] = v

    # The model omits a field it cannot fill rather than sending it empty
    # (SYSTEM_PROMPT: «НЕ выдумывай данные — если не указаны, спроси»). Declaring
    # the template's own fields as empty lets the post-processor apply its
    # defaults to them — and only to them, so an NDA never acquires an ORDER_DATE.
    for field in fields:
        data.setdefault(field, "")

    data = postprocess(data, category=db_template.category, now=now)

    still_missing = [f for f in fields if not data.get(f)]
    if still_missing:
        logger.info(
            "generate_document blocked: %d/%d fields still missing %s",
            len(still_missing),
            len(fields),
            still_missing,  # field NAMES (not values) — safe to log
        )
        return (
            "Документ НЕ создан — не хватает данных: "
            f"{', '.join(still_missing)}. "
            "Спроси эти значения у пользователя и вызови generate_document снова."
        )

    try:
        render_dir = Path(get_settings().hr_render_dir)
        render_dir.mkdir(parents=True, exist_ok=True)
        file_id = uuid.uuid4().hex[:12]
        out_path = render_dir / f"{file_id}.docx"

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
            "Document rendered: %s template=%s(id=%d) fields=%d",
            out_path,
            db_template.category,
            db_template.id,
            len(data),
        )
        return f"/api/v1/hr/documents/download/{file_id}"
    except Exception as e:
        logger.exception("Render failed for template %d", template_id)
        return f"Ошибка рендеринга: {e}"
