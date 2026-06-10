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
    GiftReportResponse,
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
    await db.flush()
    # DB-side ON DELETE SET NULL is invisible to the session — expire cached
    # objects so status history reloads request_id from the database.
    db.expire_all()
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

    # Snapshot for the error message: after rollback() the ORM object is
    # expired and attribute access would trigger sync IO (MissingGreenlet).
    target_month, target_year = plan.month, plan.year

    try:
        await db.flush()
        await db.refresh(plan)
    except IntegrityError:
        await db.rollback()
        raise BudgetPlanDuplicateError(
            f"Budget plan for {target_month:02d}.{target_year} already exists"
        ) from None
    return plan


async def delete_budget_plan(db: "AsyncSession", plan_id: int) -> bool:
    """Delete a budget plan."""
    plan = await get_budget_plan(db, plan_id)
    if plan is None:
        return False

    await db.delete(plan)
    await db.flush()
    # No SET NULL dependents on budget plans — no expire_all() needed
    # (unlike delete_gift / delete_event).
    return True


# ---------------------------------------------------------------------------
# Report service
# ---------------------------------------------------------------------------


async def get_monthly_report(
    db: "AsyncSession",
    month: int,
    year: int,
) -> GiftReportResponse:
    """Build monthly report for gift requests.

    Uses two independent queries (no JOIN) to avoid aggregation bugs
    and plan-loss on empty months.
    """
    from datetime import UTC, datetime

    start = datetime(year, month, 1, tzinfo=UTC)
    end = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=UTC)
    )

    # 1. Aggregate gifts (excluding cancelled)
    total, actual = (
        await db.execute(
            select(
                func.count(GiftRequest.id),
                func.coalesce(func.sum(GiftRequest.budget), 0),
            ).where(
                GiftRequest.created_at >= start,
                GiftRequest.created_at < end,
                GiftRequest.status != GiftStatus.CANCELLED,
            )
        )
    ).one()

    # 2. Lookup budget plan independently
    planned_result = await db.execute(
        select(GiftBudgetPlan.planned_amount).where(
            GiftBudgetPlan.month == month,
            GiftBudgetPlan.year == year,
        )
    )
    planned: int = planned_result.scalar_one_or_none() or 0

    total_requests: int = int(total)
    actual_amount: int = int(actual)
    delta = planned - actual_amount
    avg_check = round(actual_amount / total_requests) if total_requests else 0

    return GiftReportResponse(
        month=month,
        year=year,
        total_requests=total_requests,
        planned_amount=planned,
        actual_amount=actual_amount,
        delta=delta,
        avg_check=avg_check,
    )
