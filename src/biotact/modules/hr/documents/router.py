"""HR Documents API — DOCX download endpoint."""

import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from biotact.core.dependencies import CurrentUserDep
from biotact.modules.hr.documents.docx_generator import text_to_docx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr/documents", tags=["hr-documents"])


class DocxRequest(BaseModel):
    """Request body for DOCX generation."""

    text: str = Field(..., description="Document text to convert to DOCX")
    filename: str = Field("document.docx", description="Output filename")


@router.post("/download-docx")
async def download_docx(
    current_user: CurrentUserDep,
    req: DocxRequest,
) -> StreamingResponse:
    """Convert text to DOCX and return as download."""
    _ = current_user  # auth guard
    logger.info("DOCX download: filename=%s", req.filename)
    buffer = text_to_docx(req.text)

    filename = req.filename
    if not filename.endswith(".docx"):
        filename += ".docx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
