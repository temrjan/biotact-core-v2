"""Health check endpoints."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from sqlalchemy import text

from biotact import __version__
from biotact.core.database import AsyncSessionLocal
from biotact.core.dependencies import get_qdrant_service
from biotact.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


async def check_database() -> Literal["healthy", "unhealthy"]:
    """Check database connectivity."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return "healthy"
    except Exception:
        return "unhealthy"


async def check_qdrant() -> Literal["healthy", "unhealthy"]:
    """Check Qdrant connectivity."""
    try:
        qdrant_service = get_qdrant_service()
        is_healthy = await qdrant_service.health_check()
        return "healthy" if is_healthy else "unhealthy"
    except Exception:
        return "unhealthy"


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check service health and dependencies.

    Returns status of:
    - Overall service health
    - Database connectivity
    - Qdrant vector database
    """
    db_status = await check_database()
    qdrant_status = await check_qdrant()

    dependencies = {
        "database": db_status,
        "qdrant": qdrant_status,
    }

    # Determine overall status
    if all(s == "healthy" for s in dependencies.values()):
        status: Literal["healthy", "degraded", "unhealthy"] = "healthy"
    elif any(s == "unhealthy" for s in dependencies.values()):
        status = "unhealthy"
    else:
        status = "degraded"

    return HealthResponse(
        status=status,
        version=__version__,
        timestamp=datetime.now(UTC),
        dependencies=dependencies,
    )
