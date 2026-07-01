"""Unit tests for HR Gifts Report endpoint.

Covers monthly aggregation, cancelled exclusion, budget plan lookup.
Requires PostgreSQL (CI); skipped on SQLite.
"""

import os
from collections.abc import Generator
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import Settings, get_settings
from biotact.main import app
from biotact.models.user import User
from biotact.modules.hr.gifts.models import GiftBudgetPlan, GiftRequest, GiftStatus

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
    """Non-HR user receives 403 on report endpoint."""
    async_client.headers.update(auth_headers_dashboard)
    response = await async_client.get(
        "/api/v1/hr/gifts/report", params={"month": 6, "year": 2026}
    )
    assert response.status_code == 403


# =============================================================================
# CASE 1: Happy path — gifts + budget plan
# =============================================================================


@pytest.mark.asyncio
async def test_report_happy_path(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
    test_session: AsyncSession,
) -> None:
    """Report with 2 active gifts and a budget plan returns correct totals."""
    # Budget plan
    plan = GiftBudgetPlan(
        month=6, year=2026, planned_amount=5_000_000, created_by=test_user.id
    )
    test_session.add(plan)

    # Two active gifts
    for i in range(2):
        gift = GiftRequest(
            initiator="A",
            recipient="B",
            occasion="Test",
            category="Test",
            budget=1_500_000,
            status=GiftStatus.NEW,
            responsible_person_id=test_user.id,
            created_by=test_user.id,
            presentation_date=date(2026, 6, 10 + i),
            created_at=datetime(2026, 6, 10 + i, tzinfo=UTC),
        )
        test_session.add(gift)

    await test_session.commit()

    response = await authenticated_client.get(
        "/api/v1/hr/gifts/report", params={"month": 6, "year": 2026}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["month"] == 6
    assert data["year"] == 2026
    assert data["total_requests"] == 2
    assert data["planned_amount"] == 5_000_000
    assert data["actual_amount"] == 3_000_000
    assert data["delta"] == 2_000_000
    assert data["avg_check"] == 1_500_000


# =============================================================================
# CASE 2: Cancelled excluded
# =============================================================================


@pytest.mark.asyncio
async def test_report_excludes_cancelled(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
    test_session: AsyncSession,
) -> None:
    """Cancelled gifts are excluded from COUNT, SUM, and AVG."""
    # Active gift
    active = GiftRequest(
        initiator="A",
        recipient="B",
        occasion="Test",
        category="Test",
        budget=1_000_000,
        status=GiftStatus.NEW,
        responsible_person_id=test_user.id,
        created_by=test_user.id,
        presentation_date=date(2026, 6, 10),
        created_at=datetime(2026, 6, 10, tzinfo=UTC),
    )
    test_session.add(active)

    # Cancelled gift (higher budget)
    cancelled = GiftRequest(
        initiator="C",
        recipient="D",
        occasion="Test2",
        category="Test2",
        budget=9_000_000,
        status=GiftStatus.CANCELLED,
        responsible_person_id=test_user.id,
        created_by=test_user.id,
        presentation_date=date(2026, 6, 11),
        created_at=datetime(2026, 6, 11, tzinfo=UTC),
    )
    test_session.add(cancelled)

    await test_session.commit()

    response = await authenticated_client.get(
        "/api/v1/hr/gifts/report", params={"month": 6, "year": 2026}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 1
    assert data["actual_amount"] == 1_000_000
    assert data["avg_check"] == 1_000_000


# =============================================================================
# CASE 3: No budget plan
# =============================================================================


@pytest.mark.asyncio
async def test_report_no_budget_plan(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
    test_session: AsyncSession,
) -> None:
    """Gifts exist but no budget plan → planned=0, delta=-actual."""
    gift = GiftRequest(
        initiator="A",
        recipient="B",
        occasion="Test",
        category="Test",
        budget=2_000_000,
        status=GiftStatus.NEW,
        responsible_person_id=test_user.id,
        created_by=test_user.id,
        presentation_date=date(2026, 6, 10),
        created_at=datetime(2026, 6, 10, tzinfo=UTC),
    )
    test_session.add(gift)
    await test_session.commit()

    response = await authenticated_client.get(
        "/api/v1/hr/gifts/report", params={"month": 6, "year": 2026}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["planned_amount"] == 0
    assert data["actual_amount"] == 2_000_000
    assert data["delta"] == -2_000_000


# =============================================================================
# CASE 4: Empty month — no gifts, no plan
# =============================================================================


@pytest.mark.asyncio
async def test_report_empty_month(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> None:
    """No gifts and no budget plan → all zeros."""
    response = await authenticated_client.get(
        "/api/v1/hr/gifts/report", params={"month": 6, "year": 2026}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 0
    assert data["planned_amount"] == 0
    assert data["actual_amount"] == 0
    assert data["delta"] == 0
    assert data["avg_check"] == 0


# =============================================================================
# CASE 5: Plan exists, no gifts (regression guard)
# =============================================================================


@pytest.mark.asyncio
async def test_report_plan_no_gifts(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
    test_session: AsyncSession,
) -> None:
    """Budget plan exists but no gifts → planned preserved, rest zero.

    Regression guard: a JOIN-based query would lose the plan when
    gift_requests is empty. Two separate queries keep it.
    """
    plan = GiftBudgetPlan(
        month=6, year=2026, planned_amount=3_000_000, created_by=test_user.id
    )
    test_session.add(plan)
    await test_session.commit()

    response = await authenticated_client.get(
        "/api/v1/hr/gifts/report", params={"month": 6, "year": 2026}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["planned_amount"] == 3_000_000
    assert data["actual_amount"] == 0
    assert data["total_requests"] == 0
    assert data["delta"] == 3_000_000
    assert data["avg_check"] == 0


# =============================================================================
# CASE 6: Report keys on presentation_date, not created_at (date-bomb guard)
# =============================================================================


@pytest.mark.asyncio
async def test_report_keys_on_presentation_date_not_created_at(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_user: User,
    test_session: AsyncSession,
) -> None:
    """The month/year filter must key on presentation_date, not created_at.

    Wall-clock-independent: both dates are pinned. Gift A is presented in June
    but was created in January; Gift B is presented in January but was created
    in June. A June report must count only A. The old created_at-based query
    counted only B (wrong amount) and silently returned 0 once "now" moved past
    the created_at month.
    """
    presented_in_june = GiftRequest(
        initiator="A",
        recipient="B",
        occasion="Test",
        category="Test",
        budget=400_000,
        status=GiftStatus.NEW,
        responsible_person_id=test_user.id,
        created_by=test_user.id,
        presentation_date=date(2026, 6, 15),
        created_at=datetime(2026, 1, 20, tzinfo=UTC),
    )
    presented_in_january = GiftRequest(
        initiator="C",
        recipient="D",
        occasion="Test",
        category="Test",
        budget=999_000,
        status=GiftStatus.NEW,
        responsible_person_id=test_user.id,
        created_by=test_user.id,
        presentation_date=date(2026, 1, 15),
        created_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    test_session.add_all([presented_in_june, presented_in_january])
    await test_session.commit()

    response = await authenticated_client.get(
        "/api/v1/hr/gifts/report", params={"month": 6, "year": 2026}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 1  # only the June-presented gift
    assert data["actual_amount"] == 400_000  # its budget, not the 999_000 one
