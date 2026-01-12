"""Health check schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Schema for health check response."""

    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    timestamp: datetime
    dependencies: dict[str, Literal["healthy", "unhealthy"]]
