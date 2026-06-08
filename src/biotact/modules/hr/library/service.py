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

# Upload validation
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB hard limit
ALLOWED_EXTS = frozenset({"docx", "pdf", "txt", "md"})
# Magic bytes for content-type verification (text formats have no fixed signature)
_MAGIC_BYTES: dict[str, bytes] = {
    "docx": b"PK\x03\x04",  # DOCX is a ZIP archive
    "pdf": b"%PDF-",
}


class HRFileError(ValueError):
    """Base class for HR template upload validation errors."""

    status_code = 400


class HRFileTypeError(HRFileError):
    """Unsupported file extension."""


class HRFileMagicError(HRFileError):
    """Declared file type does not match content magic bytes."""


class HRFileTooLarge(HRFileError):
    """Uploaded file exceeds the size limit."""

    status_code = 413


def _ensure_upload_dir() -> None:
    """Create upload directory if it doesn't exist."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _verify_magic_bytes(ext: str, first_chunk: bytes) -> None:
    """Raise HRFileMagicError if declared ext doesn't match content header.

    Text formats (``txt``, ``md``) and any extension absent from
    ``_MAGIC_BYTES`` skip the check — they have no fixed signature.
    """
    expected_magic = _MAGIC_BYTES.get(ext)
    if expected_magic and not first_chunk.startswith(expected_magic):
        msg = f"File content does not match declared type '{ext}'."
        raise HRFileMagicError(msg)


def _extract_text_docx(file_path: str) -> str:
    """Extract full text from DOCX file (paragraphs + table cells)."""
    from docx import Document

    doc = Document(file_path)
    parts: list[str] = []
    for p in doc.paragraphs:
        if p.text.strip():
            parts.append(p.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    if p.text.strip():
                        parts.append(p.text)
    return "\n".join(parts)


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
        "md": _extract_text_txt,
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
    """Upload a template file, extract text, save to DB.

    Validates filename (strips path components), file type, content magic
    bytes (where applicable), and streams write with a hard size limit.

    Raises:
        HRFileTypeError: extension not in ALLOWED_EXTS.
        HRFileMagicError: declared type doesn't match content header.
        HRFileTooLarge: upload exceeds MAX_UPLOAD_BYTES.
    """
    _ensure_upload_dir()

    # Sanitize filename — strip any path components (cross-platform path traversal guard)
    raw_name = file.filename or "unknown"
    safe_basename = os.path.basename(raw_name.replace("\\", "/"))
    ext = safe_basename.rsplit(".", 1)[-1].lower() if "." in safe_basename else ""
    if ext not in ALLOWED_EXTS:
        msg = f"Unsupported file type: {ext or '<none>'}. Use docx, pdf, txt, or md."
        raise HRFileTypeError(msg)

    # Storage uses only uuid + ext — attacker-controlled bytes never on disk path
    storage_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = UPLOAD_DIR / storage_name

    # Verify magic bytes BEFORE persisting anything (no disk write on type mismatch)
    first_chunk = await file.read(8)
    _verify_magic_bytes(ext, first_chunk)

    # Stream the upload to disk, then extract text and persist DB row.
    # Any failure in this block (IOError, oversize, DB error, etc.) unlinks
    # the partial file — guards against orphan files on disk.
    total_size = len(first_chunk)
    try:
        with file_path.open("wb") as f:
            f.write(first_chunk)
            while chunk := await file.read(65536):
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_BYTES:
                    raise HRFileTooLarge(
                        f"Upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
                    )
                f.write(chunk)

        # Extract text
        extracted = extract_text(str(file_path), ext)

        # Scan for {{ PLACEHOLDER }} fields in DOCX templates
        fields: list[str] = []
        if ext == "docx":
            from biotact.modules.hr.library.scanner import scan_template_fields

            fields = scan_template_fields(str(file_path))

        # Save to DB — original safe_basename is the display name (UI),
        # file_path points at the uuid-named file on disk.
        template = HRTemplate(
            name=safe_basename,
            category=category,
            file_path=str(file_path),
            file_type=ext,
            file_size=total_size,
            extracted_text=extracted,
            template_fields=fields if fields else None,
            uploaded_by=user_id,
        )
        db.add(template)
        await db.flush()
        await db.refresh(template)
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    logger.info(
        "Template uploaded: id=%d name=%s category=%s fields=%s chars=%d size=%d",
        template.id,
        safe_basename,
        category,
        fields,
        len(extracted) if extracted else 0,
        total_size,
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
