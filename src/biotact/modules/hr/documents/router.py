"""HR Documents API — DOCX download endpoint."""

import logging

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from biotact.core.dependencies import CurrentUserDep
from biotact.modules.hr.documents.docx_generator import text_to_docx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr/documents", tags=["hr-documents"])


@router.post("/download-docx")
async def download_docx(
    text: str = Query(..., description="Document text to convert to DOCX"),
    filename: str = Query("document.docx", description="Output filename"),
    current_user: CurrentUserDep = ...,
) -> StreamingResponse:
    """Convert text to DOCX and return as download."""
    logger.info("DOCX download: user=%s filename=%s", current_user.email, filename)
    buffer = text_to_docx(text)

    if not filename.endswith(".docx"):
        filename += ".docx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
