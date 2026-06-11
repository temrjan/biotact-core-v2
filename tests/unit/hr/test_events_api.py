"""Unit tests for HR Events API endpoints.

Covers CRUD for calendar events.
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
    reason="HR models use PostgreSQL-specific types (ENUM, Date); requires PostgreSQL",
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
# AUTHORIZATION
# =============================================================================


@pytest.mark.asyncio
async def test_non_hr_user_forbidden(
    async_client: AsyncClient,
    auth_headers_dashboard: dict[str, str],
) -> None:
    """Non-HR user receives 403 on events endpoints."""
    async_client.headers.update(auth_headers_dashboard)
    response = await async_client.get("/api/v1/hr/events")
    assert response.status_code == 403


# =============================================================================
# CREATE
# =============================================================================


@pytest.mark.asyncio
async def test_create_event(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """POST /api/v1/hr/events creates a calendar event."""
    payload = {
        "date": "2026-06-15",
        "employee_name": "Оксана А.",
        "department": "HR",
        "occasion_type": "wedding",
        "notes": "Свадьба в офисе",
    }
    response = await authenticated_client.post("/api/v1/hr/events", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["occasion_type"] == "wedding"
    assert data["created_by"] == test_user.id


# =============================================================================
# LIST
# =============================================================================


@pytest.mark.asyncio
async def test_list_events(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_event: HREvent,
) -> None:
    """GET /api/v1/hr/events returns paginated list."""
    response = await authenticated_client.get("/api/v1/hr/events")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["size"] == 20
    assert any(item["id"] == sample_event.id for item in data["items"])


@pytest.mark.asyncio
async def test_list_events_filter_by_month_year(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """Filter events by month and year — excludes events in other months."""
    payload_june = {
        "date": "2026-06-15",
        "employee_name": "A",
        "department": "IT",
        "occasion_type": "birthday",
    }
    payload_july = {
        "date": "2026-07-15",
        "employee_name": "B",
        "department": "HR",
        "occasion_type": "wedding",
    }
    r1 = await authenticated_client.post("/api/v1/hr/events", json=payload_june)
    assert r1.status_code == 201
    june_id = r1.json()["id"]

    r2 = await authenticated_client.post("/api/v1/hr/events", json=payload_july)
    assert r2.status_code == 201
    july_id = r2.json()["id"]

    response = await authenticated_client.get(
        "/api/v1/hr/events", params={"month": 6, "year": 2026}
    )
    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["items"]}
    assert june_id in ids
    assert july_id not in ids


@pytest.mark.asyncio
async def test_list_events_filter_by_department(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """Filter events by department — excludes events in other departments."""
    payload_hr = {
        "date": "2026-06-15",
        "employee_name": "A",
        "department": "HR",
        "occasion_type": "birthday",
    }
    payload_it = {
        "date": "2026-06-16",
        "employee_name": "B",
        "department": "IT",
        "occasion_type": "wedding",
    }
    r1 = await authenticated_client.post("/api/v1/hr/events", json=payload_hr)
    assert r1.status_code == 201
    hr_id = r1.json()["id"]

    r2 = await authenticated_client.post("/api/v1/hr/events", json=payload_it)
    assert r2.status_code == 201
    it_id = r2.json()["id"]

    response = await authenticated_client.get(
        "/api/v1/hr/events", params={"department": "HR"}
    )
    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["items"]}
    assert hr_id in ids
    assert it_id not in ids


# =============================================================================
# GET BY ID
# =============================================================================


@pytest.mark.asyncio
async def test_get_event(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_event: HREvent,
) -> None:
    """GET /api/v1/hr/events/{id} returns event details."""
    response = await authenticated_client.get(f"/api/v1/hr/events/{sample_event.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_event.id
    assert data["employee_name"] == "Оксана А."


@pytest.mark.asyncio
async def test_get_event_not_found(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """GET non-existent event returns 404."""
    response = await authenticated_client.get("/api/v1/hr/events/99999")
    assert response.status_code == 404


# =============================================================================
# DELETE
# =============================================================================


@pytest.mark.asyncio
async def test_delete_event(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_event: HREvent,
) -> None:
    """DELETE /api/v1/hr/events/{id} removes the event."""
    response = await authenticated_client.delete(f"/api/v1/hr/events/{sample_event.id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = await authenticated_client.get(
        f"/api/v1/hr/events/{sample_event.id}"
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_event_not_found(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """DELETE non-existent event returns 404."""
    response = await authenticated_client.delete("/api/v1/hr/events/99999")
    assert response.status_code == 404


# =============================================================================
# SET NULL ON DELETE
# =============================================================================


@pytest.mark.asyncio
async def test_delete_event_sets_null_on_gifts(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """Deleting an event sets linked gift requests' event_id to NULL."""
    # Create event
    event_payload = {
        "date": "2026-06-15",
        "employee_name": "A",
        "department": "HR",
        "occasion_type": "birthday",
    }
    r1 = await authenticated_client.post("/api/v1/hr/events", json=event_payload)
    assert r1.status_code == 201
    event_id = r1.json()["id"]

    # Create linked gift
    gift_payload = {
        "event_id": event_id,
        "initiator": "B",
        "recipient": "C",
        "occasion": "Test",
        "category": "Test",
        "budget": 100,
    }
    r2 = await authenticated_client.post("/api/v1/hr/gifts", json=gift_payload)
    assert r2.status_code == 201
    gift_id = r2.json()["id"]
    assert r2.json()["event_id"] == event_id

    # Delete event
    r3 = await authenticated_client.delete(f"/api/v1/hr/events/{event_id}")
    assert r3.status_code == 204

    # Verify gift's event_id is NULL
    r4 = await authenticated_client.get(f"/api/v1/hr/gifts/{gift_id}")
    assert r4.status_code == 200
    assert r4.json()["event_id"] is None
