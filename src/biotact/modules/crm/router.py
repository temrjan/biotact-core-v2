"""FastAPI router for CRM endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import get_settings
from biotact.core.database import get_session
from biotact.modules.crm.schemas import (
    CustomerCreate,
    CustomerResponse,
    CustomersListResponse,
    CustomersStatsResponse,
    CustomerUpdate,
    FamilyUpdate,
    ProblemsUpdate,
    PurchaseUpdate,
)
from biotact.modules.crm.service import CRMService

router = APIRouter(prefix="/crm", tags=["crm"])
settings = get_settings()

# Type aliases
DbSession = Annotated[AsyncSession, Depends(get_session)]


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    """Verify API key for CRM endpoints."""
    if x_api_key != settings.askbiotact_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


ApiKeyDep = Annotated[None, Depends(verify_api_key)]


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/customer/{telegram_id}",
    response_model=CustomerResponse,
    summary="Get customer profile",
)
async def get_customer(
    telegram_id: int,
    db: DbSession,
    _: ApiKeyDep,
) -> CustomerResponse:
    """Get customer profile by Telegram ID."""
    service = CRMService(db)
    customer = await service.get_by_telegram_id(telegram_id)

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return CustomerResponse.model_validate(customer)


@router.post(
    "/customer",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update customer",
)
async def create_or_update_customer(
    data: CustomerCreate,
    db: DbSession,
    _: ApiKeyDep,
) -> CustomerResponse:
    """Create new customer or update existing by telegram_id."""
    service = CRMService(db)
    customer = await service.create_or_update(data)
    return CustomerResponse.model_validate(customer)


@router.patch(
    "/customer/{telegram_id}",
    response_model=CustomerResponse,
    summary="Update customer fields",
)
async def update_customer(
    telegram_id: int,
    data: CustomerUpdate,
    db: DbSession,
    _: ApiKeyDep,
) -> CustomerResponse:
    """Partially update customer fields."""
    service = CRMService(db)
    customer = await service.update(telegram_id, data)

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return CustomerResponse.model_validate(customer)


@router.patch(
    "/customer/{telegram_id}/problems",
    response_model=CustomerResponse,
    summary="Add problems/tags",
)
async def add_problems(
    telegram_id: int,
    data: ProblemsUpdate,
    db: DbSession,
    _: ApiKeyDep,
) -> CustomerResponse:
    """Add problem tags to customer profile."""
    service = CRMService(db)
    customer = await service.add_problems(telegram_id, data.problems)

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return CustomerResponse.model_validate(customer)


@router.patch(
    "/customer/{telegram_id}/family",
    response_model=CustomerResponse,
    summary="Add/update family member",
)
async def add_family_member(
    telegram_id: int,
    data: FamilyUpdate,
    db: DbSession,
    _: ApiKeyDep,
) -> CustomerResponse:
    """Add or update family member."""
    service = CRMService(db)
    customer = await service.add_family_member(telegram_id, data.member)

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return CustomerResponse.model_validate(customer)


@router.patch(
    "/customer/{telegram_id}/purchase",
    response_model=CustomerResponse,
    summary="Add purchased product",
)
async def add_purchase(
    telegram_id: int,
    data: PurchaseUpdate,
    db: DbSession,
    _: ApiKeyDep,
) -> CustomerResponse:
    """Add purchased product to customer profile."""
    service = CRMService(db)
    customer = await service.add_purchase(telegram_id, data.product)

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return CustomerResponse.model_validate(customer)


# =============================================================================
# List & Stats Endpoints
# =============================================================================


@router.get(
    "/customers",
    response_model=CustomersListResponse,
    summary="Get paginated customers list",
)
async def get_customers(
    db: DbSession,
    _: ApiKeyDep,
    page: int = 1,
    size: int = 20,
    search: str | None = None,
    problem: str | None = None,
) -> CustomersListResponse:
    """Get paginated list of customers with optional filters.

    Args:
        page: Page number (default: 1)
        size: Items per page (default: 20, max: 100)
        search: Search by name or username
        problem: Filter by problem tag (immunity, gut, stress, skin)
    """
    # Limit size
    size = min(size, 100)

    service = CRMService(db)
    customers, total = await service.get_customers_paginated(
        page=page,
        size=size,
        search=search,
        problem=problem,
    )

    pages = (total + size - 1) // size if size > 0 else 0

    return CustomersListResponse(
        items=[CustomerResponse.model_validate(c) for c in customers],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get(
    "/customers/stats",
    response_model=CustomersStatsResponse,
    summary="Get CRM statistics",
)
async def get_customers_stats(
    db: DbSession,
    _: ApiKeyDep,
) -> CustomersStatsResponse:
    """Get CRM dashboard statistics."""
    service = CRMService(db)
    stats = await service.get_stats()
    return CustomersStatsResponse(**stats)
