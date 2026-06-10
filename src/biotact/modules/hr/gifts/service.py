"""HR Gifts service — business logic for gift requests and status history."""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from biotact.modules.hr.gifts.models import (
    GiftBudgetPlan,
    GiftRequest,
    GiftStatus,
    GiftStatusHistory,
)
from biotact.modules.hr.gifts.schemas import (
    BudgetPlanCreateRequest,
    BudgetPlanListResponse,
    BudgetPlanResponse,
    BudgetPlanUpdateRequest,
    GiftCreateRequest,
    GiftHistoryResponse,
    GiftListResponse,
    GiftResponse,
    GiftStatusUpdateRequest,
    GiftUpdateRequest,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class GiftNotFoundError(ValueError):
    """Raised when a gift request is not found."""

    status_code = 404


class GiftStatusUnchangedError(ValueError):
    """Raised when status update matches current status."""

    status_code = 400


async def create_gift(
    db: "AsyncSession",
    data: GiftCreateRequest,
    user_id: int,
) -> GiftRequest:
    """Create a new gift request."""
    gift = GiftRequest(
        event_id=data.event_id,
        initiator=data.initiator,
        recipient=data.recipient,
        occasion=data.occasion,
        category=data.category,
        gift_name=data.gift_name,
        budget=data.budget,
        vendor=data.vendor,
        status=GiftStatus.NEW,
        presentation_date=data.presentation_date,
        responsible_person_id=data.responsible_person_id,
        comment=data.comment,
        created_by=user_id,
    )
    db.add(gift)
    await db.flush()
    await db.refresh(gift)
    return gift


async def list_gifts(
    db: "AsyncSession",
    *,
    status: GiftStatus | None = None,
    month: int | None = None,
    year: int | None = None,
    responsible: int | None = None,
    page: int = 1,
    size: int = 20,
) -> GiftListResponse:
    """List gift requests with optional filters and pagination.

    Filters:
        status: Filter by pipeline status.
        month + year: Filter by presentation_date month/year.
            Gifts with NULL presentation_date are excluded when
            month/year filters are active.
        responsible: Filter by responsible_person_id.
    """
    query = select(GiftRequest).order_by(GiftRequest.created_at.desc())
    count_query = select(func.count(GiftRequest.id))

    if status is not None:
        query = query.where(GiftRequest.status == status)
        count_query = count_query.where(GiftRequest.status == status)

    if month is not None and year is not None:
        start_date = date(year, month, 1)
        end_date = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        query = query.where(
            GiftRequest.presentation_date >= start_date,
            GiftRequest.presentation_date < end_date,
        )
        count_query = count_query.where(
            GiftRequest.presentation_date >= start_date,
            GiftRequest.presentation_date < end_date,
        )

    if responsible is not None:
        query = query.where(GiftRequest.responsible_person_id == responsible)
        count_query = count_query.where(
            GiftRequest.responsible_person_id == responsible
        )

    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    pages = (total + size - 1) // size if size > 0 else 0
    return GiftListResponse(
        items=[GiftResponse.model_validate(g) for g in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


async def get_gift(db: "AsyncSession", gift_id: int) -> GiftRequest | None:
    """Get a gift request by ID."""
    result = await db.execute(select(GiftRequest).where(GiftRequest.id == gift_id))
    return result.scalar_one_or_none()


async def update_gift(
    db: "AsyncSession",
    gift_id: int,
    data: GiftUpdateRequest,
) -> GiftRequest | None:
    """Partially update a gift request."""
    gift = await get_gift(db, gift_id)
    if gift is None:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(gift, field, value)

    await db.flush()
    await db.refresh(gift)
    return gift


async def update_gift_status(
    db: "AsyncSession",
    gift_id: int,
    data: GiftStatusUpdateRequest,
    user_id: int,
) -> GiftRequest | None:
    """Update gift request status and append audit record.

    Uses SELECT FOR UPDATE to prevent concurrent status modifications.
    Rejects updates where new_status equals current status.
    """
    result = await db.execute(
        select(GiftRequest).where(GiftRequest.id == gift_id).with_for_update()
    )
    gift = result.scalar_one_or_none()
    if gift is None:
        return None

    if gift.status == data.status:
        raise GiftStatusUnchangedError(f"Status is already '{data.status.value}'")

    previous_status = gift.status
    gift.status = data.status

    history = GiftStatusHistory(
        request_id=gift.id,
        from_status=previous_status,
        to_status=data.status,
        changed_by=user_id,
        comment=data.comment,
    )
    db.add(history)

    await db.flush()
    await db.refresh(gift)
    return gift


async def delete_gift(db: "AsyncSession", gift_id: int) -> bool:
    """Delete a gift request (cascades to status history via SET NULL)."""
    gift = await get_gift(db, gift_id)
    if gift is None:
        return False

    await db.delete(gift)
    return True


async def list_gift_history(
    db: "AsyncSession",
    gift_id: int,
    page: int = 1,
    size: int = 20,
) -> list[GiftHistoryResponse]:
    """List status history for a gift request."""
    query = (
        select(GiftStatusHistory)
        .where(GiftStatusHistory.request_id == gift_id)
        .order_by(GiftStatusHistory.created_at.desc())
    )
    offset = (page - 1) * size
    query = query.offset(offset).limit(size)
    result = await db.execute(query)
    items = list(result.scalars().all())
    return [GiftHistoryResponse.model_validate(h) for h in items]


# ---------------------------------------------------------------------------
# Budget Plan service
# ---------------------------------------------------------------------------


class BudgetPlanNotFoundError(ValueError):
    """Raised when a budget plan is not found."""

    status_code = 404


class BudgetPlanDuplicateError(ValueError):
    """Raised when a budget plan for month+year already exists."""

    status_code = 409


async def create_budget_plan(
    db: "AsyncSession",
    data: BudgetPlanCreateRequest,
    user_id: int,
) -> GiftBudgetPlan:
    """Create a new monthly budget plan."""
    plan = GiftBudgetPlan(
        month=data.month,
        year=data.year,
        planned_amount=data.planned_amount,
        created_by=user_id,
    )
    db.add(plan)
    try:
        await db.flush()
        await db.refresh(plan)
    except IntegrityError:
        await db.rollback()
        raise BudgetPlanDuplicateError(
            f"Budget plan for {data.month:02d}.{data.year} already exists"
        ) from None
    return plan


async def list_budget_plans(
    db: "AsyncSession",
    *,
    month: int | None = None,
    year: int | None = None,
    page: int = 1,
    size: int = 20,
) -> BudgetPlanListResponse:
    """List budget plans with optional filters and pagination."""
    query = select(GiftBudgetPlan).order_by(
        GiftBudgetPlan.year.desc(), GiftBudgetPlan.month.desc()
    )
    count_query = select(func.count(GiftBudgetPlan.id))

    if month is not None:
        query = query.where(GiftBudgetPlan.month == month)
        count_query = count_query.where(GiftBudgetPlan.month == month)

    if year is not None:
        query = query.where(GiftBudgetPlan.year == year)
        count_query = count_query.where(GiftBudgetPlan.year == year)

    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * size
    query = query.offset(offset).limit(size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    pages = (total + size - 1) // size if size > 0 else 0
    return BudgetPlanListResponse(
        items=[BudgetPlanResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


async def get_budget_plan(db: "AsyncSession", plan_id: int) -> GiftBudgetPlan | None:
    """Get a budget plan by ID."""
    result = await db.execute(
        select(GiftBudgetPlan).where(GiftBudgetPlan.id == plan_id)
    )
    return result.scalar_one_or_none()


async def update_budget_plan(
    db: "AsyncSession",
    plan_id: int,
    data: BudgetPlanUpdateRequest,
) -> GiftBudgetPlan | None:
    """Partially update a budget plan."""
    plan = await get_budget_plan(db, plan_id)
    if plan is None:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(plan, field, value)

    try:
        await db.flush()
        await db.refresh(plan)
    except IntegrityError:
        await db.rollback()
        raise BudgetPlanDuplicateError(
            f"Budget plan for {plan.month:02d}.{plan.year} already exists"
        ) from None
    return plan


async def delete_budget_plan(db: "AsyncSession", plan_id: int) -> bool:
    """Delete a budget plan."""
    plan = await get_budget_plan(db, plan_id)
    if plan is None:
        return False

    await db.delete(plan)
    return True
