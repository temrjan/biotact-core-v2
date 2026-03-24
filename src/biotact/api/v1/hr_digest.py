"""HR Digest API endpoints."""

from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Query, status

from biotact.core.dependencies import CurrentUserDep, SessionDep
from biotact.modules.hr.digest.schemas import DigestResponse
from biotact.modules.hr.digest.service import DigestService

router = APIRouter(prefix="/hr/digest", tags=["HR Digest"])


def get_digest_service() -> DigestService:
    """Get digest service instance."""
    return DigestService()


@router.get("/latest", response_model=DigestResponse)
async def get_latest_digest(
    db: SessionDep,
    current_user: CurrentUserDep,
) -> DigestResponse:
    """Get the latest HR digest.

    Returns the most recent daily digest.
    """
    service = get_digest_service()
    digest = await service.get_latest_digest(db)

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No digests found",
        )

    return digest


@router.get("/history", response_model=list[DigestResponse])
async def get_digest_history(
    db: SessionDep,
    current_user: CurrentUserDep,
    limit: int = Query(
        default=10, ge=1, le=50, description="Number of digests to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of digests to skip"),
) -> list[DigestResponse]:
    """Get digest history with pagination.

    Args:
        limit: Maximum number of digests to return (1-50).
        offset: Number of digests to skip.

    Returns:
        List of digest responses.
    """
    service = get_digest_service()
    return await service.get_digest_history(limit=limit, offset=offset, db=db)


@router.get("/{date}", response_model=DigestResponse)
async def get_digest_by_date(
    date: date_type,
    db: SessionDep,
    current_user: CurrentUserDep,
) -> DigestResponse:
    """Get digest by specific date.

    Args:
        date: Date in YYYY-MM-DD format.

    Returns:
        Digest for the specified date.

    Raises:
        HTTPException: If digest not found for this date.
    """
    service = get_digest_service()
    digest = await service.get_digest_by_date(date, db)

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No digest found for date {date}",
        )

    return digest


@router.post("/generate", response_model=DigestResponse)
async def generate_digest_manual(
    db: SessionDep,
    current_user: CurrentUserDep,
    hours: int = Query(
        default=24, ge=1, le=168, description="Hours back to scrape (1-168)"
    ),
) -> DigestResponse:
    """Manually generate a new digest.

    Args:
        hours: How many hours back to scrape news (1-168, default 24).

    Returns:
        Newly generated digest.

    Note:
        This endpoint triggers immediate scraping and summarization.
        It may take 30-60 seconds to complete.
    """
    service = get_digest_service()

    # Generate and save digest
    db_digest = await service.generate_and_save(
        db=db,
        hours=hours,
        generated_by=f"user_{current_user.id}",
    )

    # Convert to response model
    digest = await service.get_digest_by_date(db_digest.date.date(), db)

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve generated digest",
        )

    return digest
