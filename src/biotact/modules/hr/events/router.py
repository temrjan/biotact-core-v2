"""HR Events API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.database import get_session
from biotact.core.dependencies import RequireHREmailDep
from biotact.modules.hr.events import service
from biotact.modules.hr.events.schemas import (
    EventCreateRequest,
    EventListResponse,
    EventResponse,
)

router = APIRouter(prefix="/hr/events", tags=["hr-events"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=EventListResponse)
async def list_events(
    current_user: RequireHREmailDep,
    db: SessionDep,
    month: int | None = Query(
        None, ge=1, le=12, description="Filter by month"
    ),
    year: int | None = Query(
        None, ge=2000, le=2100, description="Filter by year"
    ),
    department: str | None = Query(
        None, description="Filter by department"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> EventListResponse:
    """List calendar events with optional filters and pagination."""
    _ = current_user
    return await service.list_events(
        db,
        month=month,
        year=year,
        department=department,
        page=page,
        size=size,
    )


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    current_user: RequireHREmailDep,
    db: SessionDep,
    data: EventCreateRequest,
) -> EventResponse:
    """Create a new calendar event."""
    _ = current_user
    event = await service.create_event(db, data, current_user.id)
    return EventResponse.model_validate(event)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> EventResponse:
    """Get a calendar event by ID."""
    _ = current_user
    event = await service.get_event(db, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    return EventResponse.model_validate(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> None:
    """Delete a calendar event.

    Linked gift requests will have their event_id set to NULL.
    """
    _ = current_user
    deleted = await service.delete_event(db, event_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
