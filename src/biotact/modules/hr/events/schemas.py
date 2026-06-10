"""HR Events Pydantic schemas."""

import datetime

from pydantic import BaseModel, ConfigDict, Field

from biotact.modules.hr.events.models import OccasionType


class EventCreateRequest(BaseModel):
    """Schema for creating a calendar event."""

    date: datetime.date
    employee_name: str = Field(..., max_length=300)
    department: str = Field(..., max_length=100)
    occasion_type: OccasionType
    notes: str | None = Field(None, max_length=1000)


class EventUpdateRequest(BaseModel):
    """Schema for partially updating a calendar event."""

    date: datetime.date | None = None
    employee_name: str | None = Field(None, max_length=300)
    department: str | None = Field(None, max_length=100)
    occasion_type: OccasionType | None = None
    notes: str | None = Field(None, max_length=1000)


class EventResponse(BaseModel):
    """Calendar event response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    employee_name: str
    department: str
    occasion_type: OccasionType
    notes: str | None
    created_by: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class EventListResponse(BaseModel):
    """Paginated list of calendar events."""

    items: list[EventResponse]
    total: int
    page: int
    size: int
    pages: int
