"""HR Library API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
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


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def upload_template(
    current_user: RequireHREmailDep,
    db: SessionDep,
    file: UploadFile,
    category: str = Query(
        ..., description="Template category: трудовой_договор, приказ, etc."
    ),
) -> TemplateResponse:
    """Upload a document template (DOCX/PDF/TXT)."""
    try:
        return await service.upload_template(db, file, category, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


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
