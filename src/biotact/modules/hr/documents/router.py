"""HR Documents API — render DOCX templates + download."""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.database import get_session
from biotact.core.dependencies import CurrentUserDep
from biotact.modules.hr.documents.docx_generator import text_to_docx
from biotact.modules.hr.documents.renderer import render_template
from biotact.modules.hr.library import service as library_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr/documents", tags=["hr-documents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Temp directory for rendered files
RENDER_DIR = Path("data/hr_rendered")
RENDER_DIR.mkdir(parents=True, exist_ok=True)


class DocxRequest(BaseModel):
    """Request body for text-to-DOCX generation."""

    text: str = Field(..., description="Document text to convert to DOCX")
    filename: str = Field("document.docx", description="Output filename")


class RenderRequest(BaseModel):
    """Request body for template rendering."""

    template_id: int = Field(..., description="Template ID from library")
    data: dict[str, str] = Field(
        ..., description="Placeholder values: {FIO: '...', POSITION: '...'}"
    )
    filename: str = Field("document.docx", description="Output filename")


@router.post("/download-docx")
async def download_docx(
    current_user: CurrentUserDep,
    req: DocxRequest,
) -> StreamingResponse:
    """Convert text to DOCX and return as download."""
    _ = current_user
    buffer = text_to_docx(req.text)
    filename = (
        req.filename if req.filename.endswith(".docx") else req.filename + ".docx"
    )
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/render")
async def render_docx(
    current_user: CurrentUserDep,
    db: SessionDep,
    req: RenderRequest,
) -> StreamingResponse:
    """Render a DOCX template with provided data and return as download."""
    _ = current_user

    # Get template from DB
    template = await library_service.get_template(db, req.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )

    if not template.name.endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only DOCX templates can be rendered. Upload a .docx file with {{ PLACEHOLDERS }}.",
        )

    # Find actual file path from DB
    from sqlalchemy import select

    from biotact.modules.hr.library.models import HRTemplate

    result = await db.execute(
        select(HRTemplate).where(HRTemplate.id == req.template_id)
    )
    db_template = result.scalar_one_or_none()
    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )

    # Render template
    try:
        buffer = render_template(db_template.file_path, req.data)
    except Exception as e:
        logger.exception("Failed to render template %d", req.template_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Render failed: {e}",
        ) from e

    filename = (
        req.filename if req.filename.endswith(".docx") else req.filename + ".docx"
    )

    logger.info(
        "Rendered template_id=%d fields=%d filename=%s",
        req.template_id,
        len(req.data),
        filename,
    )

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download/{file_id}")
async def download_rendered(
    file_id: str,
    current_user: CurrentUserDep,
) -> FileResponse:
    """Download a rendered DOCX by file ID."""
    _ = current_user
    file_path = RENDER_DIR / f"{file_id}.docx"
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found or expired"
        )
    return FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"document_{file_id}.docx",
    )
