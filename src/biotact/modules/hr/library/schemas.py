"""HR Library Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TemplateResponse(BaseModel):
    """Template info returned to frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    file_type: str
    file_size: int
    template_fields: list[str] | None = None
    version: int
    is_active: bool
    superseded_by_id: int | None = None
    created_at: datetime


class TemplateDetailResponse(TemplateResponse):
    """Template with extracted text and fields."""

    extracted_text: str | None = None


class TemplateListResponse(BaseModel):
    """List of templates."""

    items: list[TemplateResponse]
    total: int


# ═══════════════════════════════════════════════════════════════════
# Generated Document Schemas
# ═══════════════════════════════════════════════════════════════════


class DocumentResponse(BaseModel):
    """Generated document info."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: str
    template_name: str
    employee_name: str
    file_size: int
    created_at: datetime


class DocumentListResponse(BaseModel):
    """Paginated list of generated documents."""

    items: list[DocumentResponse]
    total: int
    page: int
    per_page: int
