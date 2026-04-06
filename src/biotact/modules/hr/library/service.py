"""HR Library service — upload, text extraction, CRUD."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from biotact.modules.hr.library.models import HRTemplate

if TYPE_CHECKING:
    from fastapi import UploadFile
    from sqlalchemy.ext.asyncio import AsyncSession
from biotact.modules.hr.library.schemas import (
    TemplateDetailResponse,
    TemplateListResponse,
    TemplateResponse,
)

logger = logging.getLogger(__name__)

# Storage directory for uploaded templates
UPLOAD_DIR = Path("data/hr_templates")


def _ensure_upload_dir() -> None:
    """Create upload directory if it doesn't exist."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _extract_text_docx(file_path: str) -> str:
    """Extract full text from DOCX file."""
    from docx import Document

    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _extract_text_pdf(file_path: str) -> str:
    """Extract full text from PDF file."""
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def _extract_text_txt(file_path: str) -> str:
    """Read plain text file."""
    with open(file_path, encoding="utf-8") as f:
        return f.read()


def extract_text(file_path: str, file_type: str) -> str | None:
    """Extract text from uploaded file based on type."""
    extractors = {
        "docx": _extract_text_docx,
        "pdf": _extract_text_pdf,
        "txt": _extract_text_txt,
    }
    extractor = extractors.get(file_type)
    if not extractor:
        logger.warning("No text extractor for file type: %s", file_type)
        return None
    try:
        return extractor(file_path)
    except Exception:
        logger.exception("Failed to extract text from %s", file_path)
        return None


async def upload_template(
    db: AsyncSession,
    file: UploadFile,
    category: str,
    user_id: int,
) -> TemplateResponse:
    """Upload a template file, extract text, save to DB."""
    _ensure_upload_dir()

    # Determine file type
    original_name = file.filename or "unknown"
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in ("docx", "pdf", "txt"):
        msg = f"Unsupported file type: {ext}. Use docx, pdf, or txt."
        raise ValueError(msg)

    # Save file to disk
    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    file_path = UPLOAD_DIR / unique_name
    content = await file.read()
    file_path.write_bytes(content)

    # Extract text
    extracted = extract_text(str(file_path), ext)

    # Save to DB
    template = HRTemplate(
        name=original_name,
        category=category,
        file_path=str(file_path),
        file_type=ext,
        file_size=len(content),
        extracted_text=extracted,
        uploaded_by=user_id,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)

    logger.info(
        "Template uploaded: id=%d name=%s category=%s chars=%d",
        template.id,
        original_name,
        category,
        len(extracted) if extracted else 0,
    )
    return TemplateResponse.model_validate(template)


async def list_templates(
    db: AsyncSession,
    category: str | None = None,
) -> TemplateListResponse:
    """List all templates, optionally filtered by category."""
    query = select(HRTemplate).order_by(HRTemplate.created_at.desc())
    if category:
        query = query.where(HRTemplate.category == category)

    result = await db.execute(query)
    items = list(result.scalars().all())

    count_query = select(func.count(HRTemplate.id))
    if category:
        count_query = count_query.where(HRTemplate.category == category)
    total = (await db.execute(count_query)).scalar_one()

    return TemplateListResponse(
        items=[TemplateResponse.model_validate(t) for t in items],
        total=total,
    )


async def get_template(
    db: AsyncSession,
    template_id: int,
) -> TemplateDetailResponse | None:
    """Get template with extracted text by ID."""
    result = await db.execute(select(HRTemplate).where(HRTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        return None
    return TemplateDetailResponse.model_validate(template)


async def get_template_by_category(
    db: AsyncSession,
    category: str,
) -> TemplateDetailResponse | None:
    """Get the most recent template for a category (for LLM tool)."""
    result = await db.execute(
        select(HRTemplate)
        .where(HRTemplate.category == category)
        .where(HRTemplate.extracted_text.is_not(None))
        .order_by(HRTemplate.created_at.desc())
        .limit(1)
    )
    template = result.scalar_one_or_none()
    if not template:
        return None
    return TemplateDetailResponse.model_validate(template)


async def delete_template(
    db: AsyncSession,
    template_id: int,
) -> bool:
    """Delete template and its file."""
    result = await db.execute(select(HRTemplate).where(HRTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        return False

    # Remove file from disk
    try:
        if os.path.exists(template.file_path):
            os.remove(template.file_path)
    except OSError:
        logger.warning("Could not delete file: %s", template.file_path)

    await db.delete(template)
    return True
