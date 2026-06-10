"""Unit tests for HR Events PATCH endpoint.

Covers partial update and 404.
Requires PostgreSQL (CI); skipped on SQLite.
"""

import os
from collections.abc import Generator
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import Settings, get_settings
from biotact.main import app
from biotact.models.user import User
from biotact.modules.hr.events.models import HREvent, OccasionType

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="HR models use PostgreSQL-specific types; requires PostgreSQL",
)


def _build_settings(allowed_emails: str) -> Settings:
    """Build settings with specific HR allowlist."""
    return Settings(
        debug=False,
        secret_key="test-secret-key-for-testing-only",
        postgres_host="localhost",
        postgres_user="biotact",
        postgres_password="biotact_test",
        postgres_db="biotact_test",
        openai_api_key="sk-test-key",
        hr_allowed_emails=allowed_emails,
    )


@pytest.fixture
def hr_allow_test_user() -> Generator[None, None, None]:
    """Override settings so test@biotact.uz is in the HR allowlist."""
    app.dependency_overrides[get_settings] = lambda: _build_settings("test@biotact.uz")
    yield


@pytest.fixture
async def sample_event(
    test_session: AsyncSession,
    test_user: User,
) -> HREvent:
    """Create a sample calendar event in the database."""
    event = HREvent(
        date=date(2026, 6, 15),
        employee_name="Оксана А.",
        department="HR",
        occasion_type=OccasionType.WEDDING,
        created_by=test_user.id,
    )
    test_session.add(event)
    await test_session.commit()
    await test_session.refresh(event)
    return event


# =============================================================================
# PARTIAL UPDATE
# =============================================================================


@pytest.mark.asyncio
async def test_update_event_partial(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_event: HREvent,
) -> None:
    """PATCH partially updates event fields without touching others."""
    payload = {"department": "IT", "notes": "Перенесли в IT"}
    response = await authenticated_client.patch(
        f"/api/v1/hr/events/{sample_event.id}", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["department"] == "IT"
    assert data["notes"] == "Перенесли в IT"
    assert data["employee_name"] == "Оксана А."  # unchanged
    assert data["occasion_type"] == "wedding"  # unchanged


@pytest.mark.asyncio
async def test_update_event_real_date(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_event: HREvent,
) -> None:
    """PATCH with a real date validates and updates correctly.

    Regression guard: field name 'date' must not shadow datetime.date
    → NoneType trap. If 'date' resolved to None, Pydantic rejects
    a real date string with a validation error.
    """
    payload = {"date": "2026-07-20"}
    response = await authenticated_client.patch(
        f"/api/v1/hr/events/{sample_event.id}", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2026-07-20"


@pytest.mark.asyncio
async def test_update_event_occasion_type(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_event: HREvent,
) -> None:
    """PATCH can update occasion_type enum field."""
    payload = {"occasion_type": "anniversary"}
    response = await authenticated_client.patch(
        f"/api/v1/hr/events/{sample_event.id}", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["occasion_type"] == "anniversary"
    assert data["employee_name"] == "Оксана А."  # unchanged


@pytest.mark.asyncio
async def test_update_event_date(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_event: HREvent,
) -> None:
    """PATCH can update date field."""
    payload = {"date": "2026-07-20"}
    response = await authenticated_client.patch(
        f"/api/v1/hr/events/{sample_event.id}", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2026-07-20"


# =============================================================================
# 404
# =============================================================================


@pytest.mark.asyncio
async def test_update_event_not_found(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """PATCH non-existent event returns 404."""
    payload = {"department": "IT"}
    response = await authenticated_client.patch("/api/v1/hr/events/99999", json=payload)
    assert response.status_code == 404
