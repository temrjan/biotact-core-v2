"""Unit tests for HR Gift Budget Plan API endpoints.

Covers CRUD and unique month+year constraint.
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
from biotact.modules.hr.gifts.models import GiftBudgetPlan

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
async def sample_budget_plan(
    test_session: AsyncSession,
    test_user: User,
) -> GiftBudgetPlan:
    """Create a sample budget plan in the database."""
    plan = GiftBudgetPlan(
        month=6,
        year=2026,
        planned_amount=5_000_000,
        created_by=test_user.id,
    )
    test_session.add(plan)
    await test_session.commit()
    await test_session.refresh(plan)
    return plan


# =============================================================================
# AUTHORIZATION
# =============================================================================


@pytest.mark.asyncio
async def test_non_hr_user_forbidden(
    async_client: AsyncClient,
    auth_headers_dashboard: dict[str, str],
) -> None:
    """Non-HR user receives 403 on budget endpoints."""
    async_client.headers.update(auth_headers_dashboard)
    response = await async_client.get("/api/v1/hr/gifts/budgets")
    assert response.status_code == 403


# =============================================================================
# CREATE
# =============================================================================


@pytest.mark.asyncio
async def test_create_budget_plan(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """POST /api/v1/hr/gifts/budgets creates a budget plan."""
    payload = {
        "month": 6,
        "year": 2026,
        "planned_amount": 5_000_000,
    }
    response = await authenticated_client.post("/api/v1/hr/gifts/budgets", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["month"] == 6
    assert data["year"] == 2026
    assert data["planned_amount"] == 5_000_000
    assert data["created_by"] == test_user.id


@pytest.mark.asyncio
async def test_create_budget_plan_duplicate_month_year(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """Creating duplicate month+year returns 409 Conflict."""
    payload = {
        "month": 7,
        "year": 2026,
        "planned_amount": 3_000_000,
    }
    r1 = await authenticated_client.post("/api/v1/hr/gifts/budgets", json=payload)
    assert r1.status_code == 201

    r2 = await authenticated_client.post("/api/v1/hr/gifts/budgets", json=payload)
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"]


# =============================================================================
# LIST
# =============================================================================


@pytest.mark.asyncio
async def test_list_budget_plans(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_budget_plan: GiftBudgetPlan,
) -> None:
    """GET /api/v1/hr/gifts/budgets returns paginated list."""
    response = await authenticated_client.get("/api/v1/hr/gifts/budgets")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["size"] == 20
    assert any(item["id"] == sample_budget_plan.id for item in data["items"])


@pytest.mark.asyncio
async def test_list_budget_plans_filter_by_month(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """Filter budget plans by month."""
    payload_june = {"month": 6, "year": 2026, "planned_amount": 1_000_000}
    payload_july = {"month": 7, "year": 2026, "planned_amount": 2_000_000}

    r1 = await authenticated_client.post("/api/v1/hr/gifts/budgets", json=payload_june)
    assert r1.status_code == 201
    june_id = r1.json()["id"]

    r2 = await authenticated_client.post("/api/v1/hr/gifts/budgets", json=payload_july)
    assert r2.status_code == 201

    response = await authenticated_client.get(
        "/api/v1/hr/gifts/budgets", params={"month": 6}
    )
    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["items"]}
    assert june_id in ids


@pytest.mark.asyncio
async def test_list_budget_plans_filter_by_year(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """Filter budget plans by year."""
    payload_2026 = {"month": 1, "year": 2026, "planned_amount": 1_000_000}
    payload_2027 = {"month": 1, "year": 2027, "planned_amount": 2_000_000}

    r1 = await authenticated_client.post("/api/v1/hr/gifts/budgets", json=payload_2026)
    assert r1.status_code == 201
    id_2026 = r1.json()["id"]

    r2 = await authenticated_client.post("/api/v1/hr/gifts/budgets", json=payload_2027)
    assert r2.status_code == 201

    response = await authenticated_client.get(
        "/api/v1/hr/gifts/budgets", params={"year": 2026}
    )
    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data["items"]}
    assert id_2026 in ids


# =============================================================================
# GET BY ID
# =============================================================================


@pytest.mark.asyncio
async def test_get_budget_plan(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_budget_plan: GiftBudgetPlan,
) -> None:
    """GET /api/v1/hr/gifts/budgets/{id} returns budget plan details."""
    response = await authenticated_client.get(
        f"/api/v1/hr/gifts/budgets/{sample_budget_plan.id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_budget_plan.id
    assert data["planned_amount"] == 5_000_000


@pytest.mark.asyncio
async def test_get_budget_plan_not_found(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """GET non-existent budget plan returns 404."""
    response = await authenticated_client.get("/api/v1/hr/gifts/budgets/99999")
    assert response.status_code == 404


# =============================================================================
# UPDATE
# =============================================================================


@pytest.mark.asyncio
async def test_update_budget_plan(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_budget_plan: GiftBudgetPlan,
) -> None:
    """PATCH /api/v1/hr/gifts/budgets/{id} partially updates a budget plan."""
    payload = {"planned_amount": 7_000_000}
    response = await authenticated_client.patch(
        f"/api/v1/hr/gifts/budgets/{sample_budget_plan.id}", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["planned_amount"] == 7_000_000
    assert data["month"] == 6  # unchanged


@pytest.mark.asyncio
async def test_update_budget_plan_duplicate_month_year(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
) -> None:
    """PATCH to month+year that already exists returns 409."""
    payload1 = {"month": 8, "year": 2026, "planned_amount": 1_000_000}
    payload2 = {"month": 9, "year": 2026, "planned_amount": 2_000_000}

    r1 = await authenticated_client.post("/api/v1/hr/gifts/budgets", json=payload1)
    assert r1.status_code == 201
    plan1_id = r1.json()["id"]

    r2 = await authenticated_client.post("/api/v1/hr/gifts/budgets", json=payload2)
    assert r2.status_code == 201

    # Try to update plan2 to plan1's month+year
    response = await authenticated_client.patch(
        f"/api/v1/hr/gifts/budgets/{plan1_id}",
        json={"month": 9, "year": 2026},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# =============================================================================
# DELETE
# =============================================================================


@pytest.mark.asyncio
async def test_delete_budget_plan(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_budget_plan: GiftBudgetPlan,
) -> None:
    """DELETE /api/v1/hr/gifts/budgets/{id} removes the budget plan."""
    response = await authenticated_client.delete(
        f"/api/v1/hr/gifts/budgets/{sample_budget_plan.id}"
    )
    assert response.status_code == 204

    get_response = await authenticated_client.get(
        f"/api/v1/hr/gifts/budgets/{sample_budget_plan.id}"
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_budget_plan_not_found(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """DELETE non-existent budget plan returns 404."""
    response = await authenticated_client.delete("/api/v1/hr/gifts/budgets/99999")
    assert response.status_code == 404
