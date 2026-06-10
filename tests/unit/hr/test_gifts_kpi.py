"""Unit tests for HR Gifts KPI endpoints.

Covers CRUD, computed percentages, duplicate guards, and auth.
Requires PostgreSQL (CI); skipped on SQLite.
"""

import os
from collections.abc import Generator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import Settings, get_settings
from biotact.main import app
from biotact.models.user import User
from biotact.modules.hr.gifts.models import GiftKPI

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
async def sample_kpi(
    test_session: AsyncSession,
    test_user: User,
) -> GiftKPI:
    """Create a sample KPI record in the database."""
    kpi = GiftKPI(
        month=6,
        year=2026,
        employee_congrats_planned=100,
        employee_congrats_actual=75,
        partner_congrats_planned=50,
        partner_congrats_actual=25,
        budget_compliance_planned=100,
        budget_compliance_actual=95,
        satisfaction_planned=10,
        satisfaction_actual=8,
        timely_closure_planned=20,
        timely_closure_actual=18,
        notes="Sample KPI notes",
        created_by=test_user.id,
    )
    test_session.add(kpi)
    await test_session.commit()
    await test_session.refresh(kpi)
    return kpi


# =============================================================================
# AUTHORIZATION
# =============================================================================


@pytest.mark.asyncio
async def test_non_hr_user_forbidden_kpi(
    async_client: AsyncClient,
    auth_headers_dashboard: dict[str, str],
) -> None:
    """Non-HR user receives 403 on KPI endpoints."""
    async_client.headers.update(auth_headers_dashboard)
    response = await async_client.get("/api/v1/hr/gifts/kpi")
    assert response.status_code == 403


# =============================================================================
# CREATE
# =============================================================================


@pytest.mark.asyncio
async def test_create_kpi_success(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """Creating a KPI with all fields returns 201 and computed percentages."""
    payload = {
        "month": 7,
        "year": 2026,
        "employee_congrats_planned": 100,
        "employee_congrats_actual": 75,
        "partner_congrats_planned": 50,
        "partner_congrats_actual": 25,
        "budget_compliance_planned": 100,
        "budget_compliance_actual": 95,
        "satisfaction_planned": 10,
        "satisfaction_actual": 8,
        "timely_closure_planned": 20,
        "timely_closure_actual": 18,
        "notes": "Q3 target",
    }
    response = await authenticated_client.post("/api/v1/hr/gifts/kpi", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["month"] == 7
    assert data["year"] == 2026
    assert data["employee_congrats_pct"] == 75
    assert data["partner_congrats_pct"] == 50
    assert data["budget_compliance_pct"] == 95
    assert data["satisfaction_pct"] == 80
    assert data["timely_closure_pct"] == 90
    assert data["notes"] == "Q3 target"


@pytest.mark.asyncio
async def test_create_kpi_duplicate_month_year(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_kpi: GiftKPI,
) -> None:
    """Creating a KPI for an existing month+year returns 409 Conflict."""
    payload = {
        "month": sample_kpi.month,
        "year": sample_kpi.year,
        "employee_congrats_planned": 1,
        "employee_congrats_actual": 1,
    }
    response = await authenticated_client.post("/api/v1/hr/gifts/kpi", json=payload)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# =============================================================================
# GET
# =============================================================================


@pytest.mark.asyncio
async def test_get_kpi_by_id(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_kpi: GiftKPI,
) -> None:
    """Getting a KPI by ID returns computed percentages."""
    response = await authenticated_client.get(f"/api/v1/hr/gifts/kpi/{sample_kpi.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_kpi.id
    assert data["employee_congrats_pct"] == 75
    assert data["partner_congrats_pct"] == 50
    assert data["budget_compliance_pct"] == 95
    assert data["satisfaction_pct"] == 80
    assert data["timely_closure_pct"] == 90


# =============================================================================
# UPDATE
# =============================================================================


@pytest.mark.asyncio
async def test_update_kpi_partial(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_kpi: GiftKPI,
) -> None:
    """Partial update changes only provided fields; others remain untouched."""
    payload = {
        "employee_congrats_planned": 200,
        "notes": "Updated notes",
    }
    response = await authenticated_client.patch(
        f"/api/v1/hr/gifts/kpi/{sample_kpi.id}", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["employee_congrats_planned"] == 200
    assert data["employee_congrats_actual"] == 75  # untouched
    assert data["partner_congrats_planned"] == 50  # untouched
    assert data["notes"] == "Updated notes"
    assert data["employee_congrats_pct"] == 38  # round(75/200*100)


# =============================================================================
# COMPUTED PERCENTAGES
# =============================================================================


@pytest.mark.asyncio
async def test_computed_pct(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """Computed percentage is 75 when actual=75 and planned=100."""
    payload = {
        "month": 8,
        "year": 2026,
        "employee_congrats_planned": 100,
        "employee_congrats_actual": 75,
    }
    response = await authenticated_client.post("/api/v1/hr/gifts/kpi", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["employee_congrats_pct"] == 75


@pytest.mark.asyncio
async def test_computed_pct_zero_planned(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """Computed percentage is 0 when planned=0 (ZeroDivision guard)."""
    payload = {
        "month": 9,
        "year": 2026,
        "employee_congrats_planned": 0,
        "employee_congrats_actual": 0,
    }
    response = await authenticated_client.post("/api/v1/hr/gifts/kpi", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["employee_congrats_pct"] == 0


# =============================================================================
# DELETE
# =============================================================================


@pytest.mark.asyncio
async def test_delete_kpi(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_kpi: GiftKPI,
) -> None:
    """Deleting a KPI returns 204 and subsequent GET returns 404."""
    kpi_id = sample_kpi.id

    response = await authenticated_client.delete(f"/api/v1/hr/gifts/kpi/{kpi_id}")
    assert response.status_code == 204

    response = await authenticated_client.get(f"/api/v1/hr/gifts/kpi/{kpi_id}")
    assert response.status_code == 404
