"""Test Alembic migration for HR gifts and events.

Requires PostgreSQL because the shipped DDL uses Postgres-specific
features (ENUM types, partial indexes). SQLite test paths via
`create_all` do NOT exercise the actual migration.
"""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Migration DDL test requires PostgreSQL",
)


@pytest.mark.asyncio
async def test_migration_upgrade_head(
    test_session: AsyncSession,
) -> None:
    """Apply migration to head and verify tables exist."""
    alembic_cfg = Config("alembic.ini")

    # Upgrade to this revision
    command.upgrade(alembic_cfg, "k9l0m1n2o345")

    # Verify tables were created
    result = await test_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN "
            "('hr_events', 'hr_gift_requests', 'hr_gift_budget_plans', "
            "'hr_gift_status_history')"
        )
    )
    tables = {row[0] for row in result.all()}
    assert tables == {
        "hr_events",
        "hr_gift_requests",
        "hr_gift_budget_plans",
        "hr_gift_status_history",
    }

    # Verify ENUM types exist
    enum_result = await test_session.execute(
        text(
            "SELECT typname FROM pg_type WHERE typname IN "
            "('hr_occasion_type', 'hr_gift_status')"
        )
    )
    enums = {row[0] for row in enum_result.all()}
    assert "hr_occasion_type" in enums
    assert "hr_gift_status" in enums


@pytest.mark.asyncio
async def test_migration_downgrade_one(
    test_session: AsyncSession,
) -> None:
    """Downgrade from this revision and verify cleanup."""
    alembic_cfg = Config("alembic.ini")

    # Ensure we are at head first
    command.upgrade(alembic_cfg, "k9l0m1n2o345")

    # Downgrade one step
    command.downgrade(alembic_cfg, "-1")

    # Verify tables were dropped
    result = await test_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN "
            "('hr_events', 'hr_gift_requests', 'hr_gift_budget_plans', "
            "'hr_gift_status_history')"
        )
    )
    tables = {row[0] for row in result.all()}
    assert tables == set()

    # Verify ENUM types were dropped
    enum_result = await test_session.execute(
        text(
            "SELECT typname FROM pg_type WHERE typname IN "
            "('hr_occasion_type', 'hr_gift_status')"
        )
    )
    enums = {row[0] for row in enum_result.all()}
    assert "hr_occasion_type" not in enums
    assert "hr_gift_status" not in enums
