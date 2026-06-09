"""HR Gifts Pydantic schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from biotact.modules.hr.gifts.models import GiftStatus


class GiftCreateRequest(BaseModel):
    """Schema for creating a gift request."""

    event_id: int | None = None
    initiator: str = Field(..., max_length=300)
    recipient: str = Field(..., max_length=300)
    occasion: str = Field(..., max_length=200)
    category: str = Field(..., max_length=100)
    gift_name: str | None = Field(None, max_length=300)
    budget: int = Field(..., ge=0)
    vendor: str | None = Field(None, max_length=200)
    presentation_date: date | None = None
    responsible_person_id: int
    comment: str | None = Field(None, max_length=1000)


class GiftUpdateRequest(BaseModel):
    """Schema for partially updating a gift request."""

    event_id: int | None = None
    initiator: str | None = Field(None, max_length=300)
    recipient: str | None = Field(None, max_length=300)
    occasion: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=100)
    gift_name: str | None = Field(None, max_length=300)
    budget: int | None = Field(None, ge=0)
    vendor: str | None = Field(None, max_length=200)
    presentation_date: date | None = None
    responsible_person_id: int | None = None
    comment: str | None = Field(None, max_length=1000)


class GiftResponse(BaseModel):
    """Gift request response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int | None
    initiator: str
    recipient: str
    occasion: str
    category: str
    gift_name: str | None
    budget: int
    vendor: str | None
    status: GiftStatus
    presentation_date: date | None
    responsible_person_id: int
    comment: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class GiftListResponse(BaseModel):
    """Paginated list of gift requests."""

    items: list[GiftResponse]
    total: int
    page: int
    size: int
    pages: int


class GiftStatusUpdateRequest(BaseModel):
    """Schema for updating gift request status."""

    status: GiftStatus
    comment: str | None = Field(None, max_length=1000)


class GiftHistoryResponse(BaseModel):
    """Gift status history response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int | None
    from_status: GiftStatus
    to_status: GiftStatus
    changed_by: int
    comment: str | None
    created_at: datetime
