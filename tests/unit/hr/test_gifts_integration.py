"""Integration tests for HR Gifts subsystem.

Exercises Budget Plan → Gift Requests → Report → KPI in a single flow.
Requires PostgreSQL (CI); skipped on SQLite.
"""

import os
from collections.abc import Generator
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import Settings, get_settings
from biotact.main import app
from biotact.models.user import User
from biotact.modules.hr.gifts.models import GiftRequest, GiftStatus

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
async def sample_gifts_for_report(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Create budget plan + 3 gifts (2 active, 1 cancelled) for report tests."""
    from biotact.modules.hr.gifts.models import GiftBudgetPlan

    plan = GiftBudgetPlan(
        month=6,
        year=2026,
        planned_amount=1_000_000,
        created_by=test_user.id,
    )
    test_session.add(plan)

    gifts = [
        GiftRequest(
            initiator="A",
            recipient="RA",
            occasion="Test",
            category="Test",
            budget=500_000,
            status=GiftStatus.NEW,
            presentation_date=date(2026, 6, 15),
            responsible_person_id=test_user.id,
            created_by=test_user.id,
        ),
        GiftRequest(
            initiator="B",
            recipient="RB",
            occasion="Test",
            category="Test",
            budget=300_000,
            status=GiftStatus.DONE,
            presentation_date=date(2026, 6, 20),
            responsible_person_id=test_user.id,
            created_by=test_user.id,
        ),
        GiftRequest(
            initiator="C",
            recipient="RC",
            occasion="Test",
            category="Test",
            budget=200_000,
            status=GiftStatus.CANCELLED,
            presentation_date=date(2026, 6, 25),
            responsible_person_id=test_user.id,
            created_by=test_user.id,
        ),
    ]
    for g in gifts:
        test_session.add(g)

    await test_session.commit()


# =============================================================================
# FULL FLOW
# =============================================================================


@pytest.mark.asyncio
async def test_full_flow_budget_gifts_report_kpi(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    sample_gifts_for_report: None,
) -> None:
    """End-to-end: budget plan → gifts → report → KPI."""
    # 1. Report should aggregate 2 non-cancelled gifts
    r_report = await authenticated_client.get(
        "/api/v1/hr/gifts/report", params={"month": 6, "year": 2026}
    )
    assert r_report.status_code == 200
    report = r_report.json()
    assert report["total_requests"] == 2
    assert report["actual_amount"] == 800_000
    assert report["planned_amount"] == 1_000_000
    assert report["delta"] == 200_000
    assert report["avg_check"] == 400_000

    # 2. Create KPI for the same month
    payload = {
        "month": 6,
        "year": 2026,
        "employee_congrats_planned": 10,
        "employee_congrats_actual": 7,
        "budget_compliance_planned": 100,
        "budget_compliance_actual": 95,
    }
    r_kpi = await authenticated_client.post("/api/v1/hr/gifts/kpi", json=payload)
    assert r_kpi.status_code == 201
    kpi = r_kpi.json()
    assert kpi["employee_congrats_pct"] == 70
    assert kpi["budget_compliance_pct"] == 95


# =============================================================================
# REPORT REGRESSIONS
# =============================================================================


@pytest.mark.asyncio
async def test_report_plan_no_gifts(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Report shows plan even when no gifts exist for the month."""
    from biotact.modules.hr.gifts.models import GiftBudgetPlan

    plan = GiftBudgetPlan(
        month=7,
        year=2026,
        planned_amount=500_000,
        created_by=test_user.id,
    )
    test_session.add(plan)
    await test_session.commit()

    r = await authenticated_client.get(
        "/api/v1/hr/gifts/report", params={"month": 7, "year": 2026}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_requests"] == 0
    assert data["actual_amount"] == 0
    assert data["planned_amount"] == 500_000
    assert data["delta"] == 500_000
    assert data["avg_check"] == 0


@pytest.mark.asyncio
async def test_report_gifts_no_plan(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Report handles missing budget plan (planned=0, delta=-actual)."""
    from datetime import UTC, datetime

    gift = GiftRequest(
        initiator="X",
        recipient="RX",
        occasion="Test",
        category="Test",
        budget=250_000,
        status=GiftStatus.NEW,
        presentation_date=date(2026, 8, 15),
        responsible_person_id=test_user.id,
        created_by=test_user.id,
        created_at=datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC),
    )
    test_session.add(gift)
    await test_session.commit()

    r = await authenticated_client.get(
        "/api/v1/hr/gifts/report", params={"month": 8, "year": 2026}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_requests"] == 1
    assert data["actual_amount"] == 250_000
    assert data["planned_amount"] == 0
    assert data["delta"] == -250_000
    assert data["avg_check"] == 250_000


# =============================================================================
# EXPLAIN / INDEX CHECK
# =============================================================================


@pytest.mark.asyncio
async def test_report_query_uses_index(
    test_session: AsyncSession,
) -> None:
    """Verify report aggregation query can use an index scan.

    This is an advisory check: on tiny tables Postgres may still pick
    Seq Scan, but we force index preference temporarily to confirm the
    plan is possible and indexes exist.
    """
    # Force index usage for the test transaction
    await test_session.execute(text("SET LOCAL enable_seqscan = off"))

    explain_result = await test_session.execute(
        text(
            """
            EXPLAIN (FORMAT TEXT)
            SELECT count(id), coalesce(sum(budget), 0)
            FROM hr_gift_requests
            WHERE created_at >= '2026-06-01'::timestamptz
              AND created_at < '2026-07-01'::timestamptz
            """
        )
    )
    plan_lines = [row[0] for row in explain_result.all()]
    plan_text = "\n".join(plan_lines).lower()

    assert "index" in plan_text, f"Expected index scan in plan, got:\n{plan_text}"
