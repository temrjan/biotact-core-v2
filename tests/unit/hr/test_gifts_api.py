"""Unit tests for HR Gifts API endpoints.

Covers CRUD, status transitions, and history.
Requires PostgreSQL (CI); skipped on SQLite.
"""

import os
from collections.abc import Generator
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import Settings, get_settings
from biotact.main import app
from biotact.models.user import User
from biotact.modules.hr.events.models import HREvent, OccasionType
from biotact.modules.hr.gifts.models import (
    GiftRequest,
    GiftStatus,
    GiftStatusHistory,
)

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
async def sample_gift(
    test_session: AsyncSession,
    test_user: User,
) -> GiftRequest:
    """Create a sample gift request in the database."""
    gift = GiftRequest(
        initiator="Павлов В.Г.",
        recipient="Оксана А.",
        occasion="Свадьба",
        category="Внешнее мероприятие",
        budget=1_500_000,
        status=GiftStatus.NEW,
        presentation_date=date(2026, 6, 15),
        responsible_person_id=test_user.id,
        created_by=test_user.id,
    )
    test_session.add(gift)
    await test_session.commit()
    await test_session.refresh(gift)
    return gift


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
    """Non-HR user receives 403 on gifts endpoints."""
    async_client.headers.update(auth_headers_dashboard)
    response = await async_client.get("/api/v1/hr/gifts")
    assert response.status_code == 403


# =============================================================================
# CREATE
# =============================================================================


@pytest.mark.asyncio
async def test_create_gift(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """POST /api/v1/hr/gifts creates a gift request."""
    payload = {
        "initiator": "Павлов В.Г.",
        "recipient": "Оксана А.",
        "occasion": "Свадьба",
        "category": "Внешнее мероприятие",
        "budget": 1_500_000,
        "presentation_date": "2026-06-15",
        "responsible_person_id": test_user.id,
    }
    response = await authenticated_client.post("/api/v1/hr/gifts", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["status"] == "new"
    assert data["budget"] == 1_500_000
    assert data["created_by"] == test_user.id


# =============================================================================
# LIST
# =============================================================================


@pytest.mark.asyncio
async def test_list_gifts(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_gift: GiftRequest,
) -> None:
    """GET /api/v1/hr/gifts returns paginated list."""
    response = await authenticated_client.get("/api/v1/hr/gifts")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["size"] == 20
    assert data["pages"] >= 1
    assert any(item["id"] == sample_gift.id for item in data["items"])


@pytest.mark.asyncio
async def test_list_gifts_filter_by_status(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """Filter gifts by status — excludes gifts with different status."""
    payload_new = {
        "initiator": "A",
        "recipient": "B",
        "occasion": "Test",
        "category": "Test",
        "budget": 100,
        "responsible_person_id": test_user.id,
    }
    payload_approval = {
        "initiator": "C",
        "recipient": "D",
        "occasion": "Test2",
        "category": "Test2",
        "budget": 200,
        "responsible_person_id": test_user.id,
    }
    r1 = await authenticated_client.post("/api/v1/hr/gifts", json=payload_new)
    assert r1.status_code == 201
    new_id = r1.json()["id"]

    r2 = await authenticated_client.post("/api/v1/hr/gifts", json=payload_approval)
    assert r2.status_code == 201
    approval_id = r2.json()["id"]

    # Move second gift to approval
    r3 = await authenticated_client.patch(
        f"/api/v1/hr/gifts/{approval_id}/status",
        json={"status": "approval"},
    )
    assert r3.status_code == 200

    response = await authenticated_client.get(
        "/api/v1/hr/gifts", params={"status": "new"}
    )
    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["items"]}
    assert new_id in ids
    assert approval_id not in ids


@pytest.mark.asyncio
async def test_list_gifts_filter_by_month_year(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """Filter gifts by presentation month and year — excludes other months."""
    payload_june = {
        "initiator": "A",
        "recipient": "B",
        "occasion": "Test",
        "category": "Test",
        "budget": 100,
        "presentation_date": "2026-06-15",
        "responsible_person_id": test_user.id,
    }
    payload_july = {
        "initiator": "C",
        "recipient": "D",
        "occasion": "Test2",
        "category": "Test2",
        "budget": 200,
        "presentation_date": "2026-07-15",
        "responsible_person_id": test_user.id,
    }
    r1 = await authenticated_client.post("/api/v1/hr/gifts", json=payload_june)
    assert r1.status_code == 201
    june_id = r1.json()["id"]

    r2 = await authenticated_client.post("/api/v1/hr/gifts", json=payload_july)
    assert r2.status_code == 201
    july_id = r2.json()["id"]

    response = await authenticated_client.get(
        "/api/v1/hr/gifts", params={"month": 6, "year": 2026}
    )
    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["items"]}
    assert june_id in ids
    assert july_id not in ids


# =============================================================================
# GET BY ID
# =============================================================================


@pytest.mark.asyncio
async def test_get_gift(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_gift: GiftRequest,
) -> None:
    """GET /api/v1/hr/gifts/{id} returns gift details."""
    response = await authenticated_client.get(f"/api/v1/hr/gifts/{sample_gift.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_gift.id
    assert data["recipient"] == "Оксана А."


@pytest.mark.asyncio
async def test_get_gift_not_found(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """GET non-existent gift returns 404."""
    response = await authenticated_client.get("/api/v1/hr/gifts/99999")
    assert response.status_code == 404


# =============================================================================
# UPDATE
# =============================================================================


@pytest.mark.asyncio
async def test_update_gift(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_gift: GiftRequest,
) -> None:
    """PATCH /api/v1/hr/gifts/{id} partially updates a gift."""
    payload = {"budget": 2_000_000, "gift_name": "Пылесос"}
    response = await authenticated_client.patch(
        f"/api/v1/hr/gifts/{sample_gift.id}", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["budget"] == 2_000_000
    assert data["gift_name"] == "Пылесос"
    assert data["recipient"] == "Оксана А."  # unchanged


# =============================================================================
# STATUS TRANSITION
# =============================================================================


@pytest.mark.asyncio
async def test_update_gift_status(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_gift: GiftRequest,
    test_user: User,
) -> None:
    """PATCH /status changes status and creates audit record."""
    payload = {"status": "approval", "comment": "Согласовано"}
    response = await authenticated_client.patch(
        f"/api/v1/hr/gifts/{sample_gift.id}/status", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approval"

    # Verify history was created
    history_response = await authenticated_client.get(
        f"/api/v1/hr/gifts/{sample_gift.id}/history"
    )
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["from_status"] == "new"
    assert history[0]["to_status"] == "approval"
    assert history[0]["changed_by"] == test_user.id


@pytest.mark.asyncio
async def test_update_gift_status_unchanged(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_gift: GiftRequest,
) -> None:
    """PATCH /status with same status returns 400."""
    payload = {"status": "new"}
    response = await authenticated_client.patch(
        f"/api/v1/hr/gifts/{sample_gift.id}/status", json=payload
    )
    assert response.status_code == 400


# =============================================================================
# DELETE
# =============================================================================


@pytest.mark.asyncio
async def test_delete_gift(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_gift: GiftRequest,
) -> None:
    """DELETE /api/v1/hr/gifts/{id} removes the gift."""
    response = await authenticated_client.delete(f"/api/v1/hr/gifts/{sample_gift.id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = await authenticated_client.get(f"/api/v1/hr/gifts/{sample_gift.id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_gift_not_found(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """DELETE non-existent gift returns 404."""
    response = await authenticated_client.delete("/api/v1/hr/gifts/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_gift_sets_null_on_history(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_gift: GiftRequest,
    test_session: AsyncSession,
) -> None:
    """Deleting a gift via API sets history request_id to NULL (service path).

    Regression guard for service.delete_gift's flush() + expire_all():
    the DB-side ON DELETE SET NULL only becomes visible because the
    service flushes the DELETE and expires cached rows.
    """
    gift_id = sample_gift.id

    # Create a history row via the status endpoint
    r1 = await authenticated_client.patch(
        f"/api/v1/hr/gifts/{gift_id}/status",
        json={"status": "approval"},
    )
    assert r1.status_code == 200

    r2 = await authenticated_client.get(f"/api/v1/hr/gifts/{gift_id}/history")
    assert r2.status_code == 200
    history_ids = [h["id"] for h in r2.json()]
    assert history_ids

    # Delete via API — exercises service.delete_gift (flush + expire_all)
    r3 = await authenticated_client.delete(f"/api/v1/hr/gifts/{gift_id}")
    assert r3.status_code == 204

    # History must survive with request_id NULL
    result = await test_session.execute(
        select(GiftStatusHistory).where(GiftStatusHistory.id.in_(history_ids))
    )
    records = result.scalars().all()
    assert len(records) == len(history_ids)
    assert all(r.request_id is None for r in records)


# =============================================================================
# HISTORY
# =============================================================================


@pytest.mark.asyncio
async def test_list_gift_history_empty(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_gift: GiftRequest,
) -> None:
    """History for a new gift with no transitions is empty."""
    response = await authenticated_client.get(
        f"/api/v1/hr/gifts/{sample_gift.id}/history"
    )
    assert response.status_code == 200
    data = response.json()
    assert data == []


# =============================================================================
# EVENT RELATIONSHIP
# =============================================================================


@pytest.mark.asyncio
async def test_create_gift_with_event(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
    sample_event: HREvent,
) -> None:
    """Gift can be linked to an event."""
    payload = {
        "event_id": sample_event.id,
        "initiator": "Павлов В.Г.",
        "recipient": "Оксана А.",
        "occasion": "Свадьба",
        "category": "Внешнее мероприятие",
        "budget": 1_500_000,
        "responsible_person_id": test_user.id,
    }
    response = await authenticated_client.post("/api/v1/hr/gifts", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["event_id"] == sample_event.id
