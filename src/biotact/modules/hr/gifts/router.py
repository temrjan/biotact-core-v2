"""HR Gifts API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.database import get_session
from biotact.core.dependencies import RequireHREmailDep
from biotact.modules.hr.gifts import service
from biotact.modules.hr.gifts.models import GiftStatus
from biotact.modules.hr.gifts.schemas import (
    GiftCreateRequest,
    GiftHistoryResponse,
    GiftListResponse,
    GiftResponse,
    GiftStatusUpdateRequest,
    GiftUpdateRequest,
)

router = APIRouter(prefix="/hr/gifts", tags=["hr-gifts"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=GiftListResponse)
async def list_gifts(
    current_user: RequireHREmailDep,
    db: SessionDep,
    status: GiftStatus | None = Query(  # noqa: B008
        None, description="Filter by status"
    ),
    month: int | None = Query(
        None, ge=1, le=12, description="Filter by presentation month"
    ),
    year: int | None = Query(
        None, ge=2000, le=2100, description="Filter by presentation year"
    ),
    responsible: int | None = Query(
        None, description="Filter by responsible person ID"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> GiftListResponse:
    """List gift requests with optional filters and pagination."""
    _ = current_user
    return await service.list_gifts(
        db,
        status=status,
        month=month,
        year=year,
        responsible=responsible,
        page=page,
        size=size,
    )


@router.post("", response_model=GiftResponse, status_code=status.HTTP_201_CREATED)
async def create_gift(
    current_user: RequireHREmailDep,
    db: SessionDep,
    data: GiftCreateRequest,
) -> GiftResponse:
    """Create a new gift request."""
    _ = current_user
    gift = await service.create_gift(db, data, current_user.id)
    return GiftResponse.model_validate(gift)


@router.get("/{gift_id}", response_model=GiftResponse)
async def get_gift(
    gift_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> GiftResponse:
    """Get a gift request by ID."""
    _ = current_user
    gift = await service.get_gift(db, gift_id)
    if gift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gift request not found",
        )
    return GiftResponse.model_validate(gift)


@router.patch("/{gift_id}", response_model=GiftResponse)
async def update_gift(
    gift_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
    data: GiftUpdateRequest,
) -> GiftResponse:
    """Partially update a gift request."""
    _ = current_user
    gift = await service.update_gift(db, gift_id, data)
    if gift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gift request not found",
        )
    return GiftResponse.model_validate(gift)


@router.patch("/{gift_id}/status", response_model=GiftResponse)
async def update_gift_status(
    gift_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
    data: GiftStatusUpdateRequest,
) -> GiftResponse:
    """Update gift request status and append audit record."""
    _ = current_user
    try:
        gift = await service.update_gift_status(db, gift_id, data, current_user.id)
    except service.GiftStatusUnchangedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    if gift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gift request not found",
        )
    return GiftResponse.model_validate(gift)


@router.delete("/{gift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gift(
    gift_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
) -> None:
    """Delete a gift request."""
    _ = current_user
    deleted = await service.delete_gift(db, gift_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gift request not found",
        )


@router.get("/{gift_id}/history", response_model=list[GiftHistoryResponse])
async def list_gift_history(
    gift_id: int,
    current_user: RequireHREmailDep,
    db: SessionDep,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> list[GiftHistoryResponse]:
    """List status history for a gift request."""
    _ = current_user
    return await service.list_gift_history(db, gift_id, page=page, size=size)
