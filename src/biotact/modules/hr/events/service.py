"""HR Events service — business logic for calendar events."""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from biotact.modules.hr.events.models import HREvent
from biotact.modules.hr.events.schemas import (
    EventCreateRequest,
    EventListResponse,
    EventResponse,
    EventUpdateRequest,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create_event(
    db: "AsyncSession",
    data: EventCreateRequest,
    user_id: int,
) -> HREvent:
    """Create a new calendar event."""
    event = HREvent(
        date=data.date,
        employee_name=data.employee_name,
        department=data.department,
        occasion_type=data.occasion_type,
        notes=data.notes,
        created_by=user_id,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


async def list_events(
    db: "AsyncSession",
    *,
    month: int | None = None,
    year: int | None = None,
    department: str | None = None,
    page: int = 1,
    size: int = 20,
) -> EventListResponse:
    """List calendar events with optional filters and pagination.

    Filters:
        month + year: Filter by event date month/year.
        department: Filter by department name (exact match).
    """
    query = select(HREvent).order_by(HREvent.date.desc())
    count_query = select(func.count(HREvent.id))

    if month is not None and year is not None:
        start_date = date(year, month, 1)
        end_date = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        query = query.where(
            HREvent.date >= start_date,
            HREvent.date < end_date,
        )
        count_query = count_query.where(
            HREvent.date >= start_date,
            HREvent.date < end_date,
        )

    if department is not None:
        query = query.where(HREvent.department == department)
        count_query = count_query.where(HREvent.department == department)

    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    pages = (total + size - 1) // size if size > 0 else 0
    return EventListResponse(
        items=[EventResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


async def get_event(db: "AsyncSession", event_id: int) -> HREvent | None:
    """Get a calendar event by ID."""
    result = await db.execute(select(HREvent).where(HREvent.id == event_id))
    return result.scalar_one_or_none()


async def update_event(
    db: "AsyncSession",
    event_id: int,
    data: EventUpdateRequest,
) -> HREvent | None:
    """Partially update a calendar event."""
    event = await get_event(db, event_id)
    if event is None:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(event, field, value)

    await db.flush()
    await db.refresh(event)
    return event


async def delete_event(db: "AsyncSession", event_id: int) -> bool:
    """Delete a calendar event.

    Linked gift requests will have their event_id set to NULL
    via the existing SET NULL foreign key constraint.
    """
    event = await get_event(db, event_id)
    if event is None:
        return False

    await db.delete(event)
    return True
