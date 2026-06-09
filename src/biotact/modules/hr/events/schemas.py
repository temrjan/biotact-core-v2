"""HR Events Pydantic schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from biotact.modules.hr.events.models import OccasionType


class EventCreateRequest(BaseModel):
    """Schema for creating a calendar event."""

    date: date
    employee_name: str = Field(..., max_length=300)
    department: str = Field(..., max_length=100)
    occasion_type: OccasionType
    notes: str | None = Field(None, max_length=1000)


class EventResponse(BaseModel):
    """Calendar event response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    employee_name: str
    department: str
    occasion_type: OccasionType
    notes: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class EventListResponse(BaseModel):
    """Paginated list of calendar events."""

    items: list[EventResponse]
    total: int
    page: int
    size: int
    pages: int
