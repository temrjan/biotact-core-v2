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
    created_at: datetime


class TemplateDetailResponse(TemplateResponse):
    """Template with extracted text and fields."""

    extracted_text: str | None = None


class TemplateListResponse(BaseModel):
    """List of templates."""

    items: list[TemplateResponse]
    total: int
