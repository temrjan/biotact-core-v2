"""HR Library API endpoints."""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.database import get_session
from biotact.core.dependencies import RequireHREmailDep
from biotact.modules.hr.library import service
from biotact.modules.hr.library.schemas import (
    TemplateDetailResponse,
    TemplateListResponse,
    TemplateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr/library", tags=["hr-library"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Media types for template file downloads, keyed by stored file_type.
_MEDIA_TYPES: dict[str, str] = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
}
_DEFAULT_MEDIA_TYPE = "application/octet-stream"


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def upload_template(
    current_user: RequireHREmailDep,
    db: SessionDep,
    file: UploadFile,
    category: str = Query(
        ...,
        description=(
            "Template category — one of the keys the extraction rules are "
            "written for: td_osnovnoy, td_sovmestitelstvo, gpd_uslugi, "
            "prikaz_priem, prikaz_avto, mat_otvetstvennost, "
            "dop_soglashenie_pasport, nda_rabotnik, nda_gpd, "
            "soglashenie_vozmeshenie, soglashenie_pd. Anything else is "
            "accepted but degrades extraction to the common rules."
        ),
    ),
    confirm: bool = Query(
        False,
        description="Proceed even if the upload drops placeholders the active version had.",
    ),
) -> TemplateResponse:
    """Upload a document template (DOCX/PDF/TXT). Re-upload to a category replaces it."""
    try:
        return await service.upload_template(
            db, file, category, current_user.id, confirm=confirm
        )
    except service.HRTemplateDroppedFieldsError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "code": "dropped_placeholders",
                "dropped": e.dropped,
                "message": str(e),
            },
        ) from e
    except service.HRTemplateConflictError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
    except service.HRFileError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    current_user: RequireHREmailDep,
    db: SessionDep,
    category: str | None = Query(None, description="Filter by category"),
) -> TemplateListResponse:
    """List all templates, optionally filtered by category."""
    _ = current_user  # auth guard
    return await service.list_templates(db, category)


@router.get("/{template_id}", response_model=TemplateDetailResponse)
async def get_template(
    template_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> TemplateDetailResponse:
    """Get template details with extracted text."""
    _ = current_user  # auth guard
    result = await service.get_template(db, template_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    return result


@router.get("/{template_id}/download")
async def download_template(
    template_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> FileResponse:
    """Download the raw template file by ID (to edit in Word, then re-upload)."""
    _ = current_user  # auth guard
    template = await service.get_template_file(db, template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    # FileResponse raises 500 on a missing path — guard explicitly so a stale row
    # (file removed from disk) returns a clean 404 instead.
    file_path = Path(template.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template file not found"
        )
    return FileResponse(
        path=str(file_path),
        filename=template.name,
        media_type=_MEDIA_TYPES.get(template.file_type, _DEFAULT_MEDIA_TYPE),
    )


@router.get("/{category}/history", response_model=TemplateListResponse)
async def list_template_history(
    category: str,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> TemplateListResponse:
    """List all versions of templates for a category."""
    _ = current_user  # auth guard
    items = await service.list_template_history(db, category)
    return TemplateListResponse(items=items, total=len(items))


@router.post("/{template_id}/rollback", response_model=TemplateResponse)
async def rollback_template(
    template_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> TemplateResponse:
    """Rollback category to the specified template version."""
    _ = current_user  # auth guard
    try:
        result = await service.rollback_template(db, template_id)
    except service.HRFileError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return TemplateResponse.model_validate(result)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> None:
    """Delete a template."""
    _ = current_user  # auth guard
    deleted = await service.delete_template(db, template_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
