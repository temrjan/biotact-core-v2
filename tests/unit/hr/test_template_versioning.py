"""Tests for HRTemplate versioning schema constraints.

Requires PostgreSQL because HRTemplate uses JSONB columns and partial unique
indexes that SQLite cannot render.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.models.user import User
from biotact.modules.hr.library.models import HRTemplate

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="HR models use JSONB columns; requires PostgreSQL",
)


@pytest.mark.asyncio
async def test_default_version_and_active(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """New templates default to version=1 and is_active=True."""
    await test_session.execute(text("DELETE FROM hr_templates"))
    await test_session.commit()

    template = HRTemplate(
        name="Test Contract",
        category="трудовой_договор_default",
        file_path="data/hr/test.docx",
        file_type="docx",
        file_size=1024,
        uploaded_by=test_user.id,
    )
    test_session.add(template)
    await test_session.commit()
    await test_session.refresh(template)

    assert template.version == 1
    assert template.is_active is True
    assert template.superseded_by_id is None


@pytest.mark.asyncio
async def test_unique_constraint_category_version(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Duplicate (category, version) pairs must raise IntegrityError."""
    await test_session.execute(text("DELETE FROM hr_templates"))
    await test_session.commit()

    t1 = HRTemplate(
        name="Contract v1",
        category="трудовой_договор_unique",
        file_path="data/hr/t1.docx",
        file_type="docx",
        file_size=1024,
        uploaded_by=test_user.id,
        version=1,
    )
    test_session.add(t1)
    await test_session.commit()

    t2 = HRTemplate(
        name="Contract v1 again",
        category="трудовой_договор_unique",
        file_path="data/hr/t2.docx",
        file_type="docx",
        file_size=1024,
        uploaded_by=test_user.id,
        version=1,
    )
    test_session.add(t2)
    with pytest.raises(IntegrityError):
        await test_session.commit()

    await test_session.rollback()


@pytest.mark.asyncio
async def test_partial_unique_index_active_per_category(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Only one is_active=True template is allowed per category."""
    await test_session.execute(text("DELETE FROM hr_templates"))
    await test_session.commit()

    t1 = HRTemplate(
        name="Active Contract",
        category="трудовой_договор_partial",
        file_path="data/hr/active.docx",
        file_type="docx",
        file_size=1024,
        uploaded_by=test_user.id,
        is_active=True,
    )
    test_session.add(t1)
    await test_session.commit()

    # Inactive template in the same category is allowed.
    t2 = HRTemplate(
        name="Inactive Contract",
        category="трудовой_договор_partial",
        file_path="data/hr/inactive.docx",
        file_type="docx",
        file_size=1024,
        uploaded_by=test_user.id,
        is_active=False,
        version=2,
    )
    test_session.add(t2)
    await test_session.commit()

    # Another active template in the same category must fail.
    t3 = HRTemplate(
        name="Another Active Contract",
        category="трудовой_договор_partial",
        file_path="data/hr/active2.docx",
        file_type="docx",
        file_size=1024,
        uploaded_by=test_user.id,
        is_active=True,
        version=3,
    )
    test_session.add(t3)
    with pytest.raises(IntegrityError):
        await test_session.commit()

    await test_session.rollback()
