"""Tests for HR Gifts and Events models.

Covers creation, defaults, constraints, and relationships.
Works with both SQLite (local) and PostgreSQL (CI).
"""

import os
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.models.user import User
from biotact.modules.hr.events.models import HREvent, OccasionType
from biotact.modules.hr.gifts.models import (
    GiftBudgetPlan,
    GiftRequest,
    GiftStatus,
    GiftStatusHistory,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="HR models use PostgreSQL-specific types (ENUM, Date); requires PostgreSQL",
)

# =============================================================================
# HREvent
# =============================================================================


@pytest.mark.asyncio
async def test_create_hr_event(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Create a calendar event."""
    event = HREvent(
        date=date(2026, 6, 15),
        employee_name="Оксана А.",
        department="HR",
        occasion_type=OccasionType.WEDDING,
        notes="Свадьба в офисе",
        created_by=test_user.id,
    )
    test_session.add(event)
    await test_session.commit()
    await test_session.refresh(event)

    assert event.id is not None
    assert event.occasion_type == OccasionType.WEDDING
    assert event.created_at is not None


@pytest.mark.asyncio
async def test_hr_event_all_occasion_types(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """All occasion types can be persisted."""
    for occ_type in OccasionType:
        event = HREvent(
            date=date(2026, 6, 9),
            employee_name="Test",
            department="IT",
            occasion_type=occ_type,
            created_by=test_user.id,
        )
        test_session.add(event)

    await test_session.commit()

    result = await test_session.execute(select(HREvent))
    events = result.scalars().all()
    assert len(events) == len(OccasionType)


# =============================================================================
# GiftRequest
# =============================================================================


@pytest.mark.asyncio
async def test_create_gift_request(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Create a gift request with all fields."""
    request = GiftRequest(
        initiator="Павлов В.Г.",
        recipient="Оксана А.",
        occasion="Свадьба",
        category="Внешнее мероприятие",
        gift_name="Аэрогриль",
        budget=1_500_000,
        vendor="MediaMarkt",
        status=GiftStatus.NEW,
        presentation_date=date(2026, 6, 15),
        responsible_person_id=test_user.id,
        comment="Упаковка + открытка",
        created_by=test_user.id,
    )
    test_session.add(request)
    await test_session.commit()
    await test_session.refresh(request)

    assert request.id is not None
    assert request.status == GiftStatus.NEW
    assert request.budget == 1_500_000
    assert request.created_at is not None
    assert request.updated_at is not None


@pytest.mark.asyncio
async def test_gift_request_defaults(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Default values are applied correctly."""
    request = GiftRequest(
        initiator="Test",
        recipient="Test",
        occasion="Test",
        category="Test",
        responsible_person_id=test_user.id,
        created_by=test_user.id,
    )
    test_session.add(request)
    await test_session.commit()
    await test_session.refresh(request)

    assert request.status == GiftStatus.NEW
    assert request.budget == 0
    assert request.gift_name is None


@pytest.mark.asyncio
async def test_gift_request_all_statuses(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """All pipeline statuses can be persisted."""
    for idx, status in enumerate(GiftStatus):
        request = GiftRequest(
            initiator=f"Initiator {idx}",
            recipient=f"Recipient {idx}",
            occasion="Test",
            category="Test",
            status=status,
            responsible_person_id=test_user.id,
            created_by=test_user.id,
        )
        test_session.add(request)

    await test_session.commit()

    result = await test_session.execute(select(GiftRequest))
    requests = result.scalars().all()
    assert len(requests) == len(GiftStatus)


@pytest.mark.asyncio
async def test_gift_request_event_relationship(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """GiftRequest can link to HREvent."""
    event = HREvent(
        date=date(2026, 6, 15),
        employee_name="Оксана А.",
        department="HR",
        occasion_type=OccasionType.WEDDING,
        created_by=test_user.id,
    )
    test_session.add(event)
    await test_session.flush()

    request = GiftRequest(
        event_id=event.id,
        initiator="Павлов В.Г.",
        recipient="Оксана А.",
        occasion="Свадьба",
        category="Внешнее мероприятие",
        responsible_person_id=test_user.id,
        created_by=test_user.id,
    )
    test_session.add(request)
    await test_session.commit()
    await test_session.refresh(request)

    assert request.event_id == event.id


# =============================================================================
# GiftBudgetPlan
# =============================================================================


@pytest.mark.asyncio
async def test_create_gift_budget_plan(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Create a monthly budget plan."""
    plan = GiftBudgetPlan(
        month=6,
        year=2026,
        planned_amount=18_000_000,
        created_by=test_user.id,
    )
    test_session.add(plan)
    await test_session.commit()
    await test_session.refresh(plan)

    assert plan.id is not None
    assert plan.month == 6
    assert plan.year == 2026


@pytest.mark.asyncio
async def test_unique_budget_plan_month_year(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Duplicate (month, year) plans are rejected."""
    plan1 = GiftBudgetPlan(
        month=6,
        year=2026,
        planned_amount=10_000_000,
        created_by=test_user.id,
    )
    test_session.add(plan1)
    await test_session.commit()

    plan2 = GiftBudgetPlan(
        month=6,
        year=2026,
        planned_amount=20_000_000,
        created_by=test_user.id,
    )
    test_session.add(plan2)

    with pytest.raises(IntegrityError):
        await test_session.commit()

    await test_session.rollback()


# =============================================================================
# GiftStatusHistory
# =============================================================================


@pytest.mark.asyncio
async def test_create_status_history(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Audit record is created for a status transition."""
    request = GiftRequest(
        initiator="Test",
        recipient="Test",
        occasion="Test",
        category="Test",
        status=GiftStatus.NEW,
        responsible_person_id=test_user.id,
        created_by=test_user.id,
    )
    test_session.add(request)
    await test_session.flush()

    history = GiftStatusHistory(
        request_id=request.id,
        from_status=GiftStatus.NEW,
        to_status=GiftStatus.APPROVAL,
        changed_by=test_user.id,
        comment="Согласовано руководителем",
    )
    test_session.add(history)
    await test_session.commit()
    await test_session.refresh(history)

    assert history.id is not None
    assert history.from_status == GiftStatus.NEW
    assert history.to_status == GiftStatus.APPROVAL
    assert history.created_at is not None


@pytest.mark.asyncio
async def test_status_history_set_null_on_delete(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Deleting a gift request sets history request_id to NULL (append-only)."""
    request = GiftRequest(
        initiator="Test",
        recipient="Test",
        occasion="Test",
        category="Test",
        responsible_person_id=test_user.id,
        created_by=test_user.id,
    )
    test_session.add(request)
    await test_session.flush()

    history = GiftStatusHistory(
        request_id=request.id,
        from_status=GiftStatus.NEW,
        to_status=GiftStatus.DONE,
        changed_by=test_user.id,
    )
    test_session.add(history)
    await test_session.commit()
    history_id = history.id

    # Delete request
    await test_session.delete(request)
    await test_session.commit()

    # History should survive with NULL request_id
    result = await test_session.execute(
        select(GiftStatusHistory).where(GiftStatusHistory.id == history_id)
    )
    record = result.scalar_one()
    assert record.request_id is None
    assert record.from_status == GiftStatus.NEW
    assert record.to_status == GiftStatus.DONE
