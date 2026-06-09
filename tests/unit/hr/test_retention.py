"""Tests for HR document retention policy (PR-9).

Requires PostgreSQL because HRTemplate uses JSONB columns.
"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.models.user import User
from biotact.modules.hr.library.models import HRDocument, HRTemplate
from biotact.modules.hr.retention import cleanup_old_documents

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="HR models use JSONB columns; requires PostgreSQL",
)


MINIMAL_DOCX = b"PK\x03\x04" + b"\x00" * 200


@pytest_asyncio.fixture
async def retention_user(test_session: AsyncSession) -> User:
    """Create a test user for retention tests."""
    user = User(
        email="retention@biotact.uz",
        hashed_password="test",
        full_name="Retention User",
        department_id="hr",
        is_active=True,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def td_template(test_session: AsyncSession) -> HRTemplate:
    """Create an active template in the td_osnovnoy category."""
    template = HRTemplate(
        name="td_osnovnoy.docx",
        category="td_osnovnoy",
        file_path="data/hr_templates/td_osnovnoy_v1.docx",
        file_type="docx",
        file_size=len(MINIMAL_DOCX),
        version=1,
        is_active=True,
        uploaded_by=1,
    )
    test_session.add(template)
    await test_session.commit()
    await test_session.refresh(template)
    return template


@pytest.mark.asyncio
async def test_old_document_is_deleted(
    test_session: AsyncSession,
    retention_user: User,
    td_template: HRTemplate,
    tmp_path: Path,
) -> None:
    """Document older than 30 days is hard-deleted (file + DB row)."""
    # Create a file on disk
    doc_file = tmp_path / "old_doc.docx"
    doc_file.write_bytes(MINIMAL_DOCX)

    now = datetime.now(UTC)
    old_date = now - timedelta(days=31)

    doc = HRDocument(
        file_id="old123",
        template_id=td_template.id,
        template_name="td_osnovnoy.docx",
        employee_name="Test Employee",
        file_path=str(doc_file),
        file_size=len(MINIMAL_DOCX),
        created_by=retention_user.id,
        created_at=old_date,
    )
    test_session.add(doc)
    await test_session.commit()
    await test_session.refresh(doc)

    deleted = await cleanup_old_documents(test_session, now, retention_days=30)
    await test_session.commit()

    assert deleted == 1
    assert not doc_file.exists()

    result = await test_session.execute(
        select(HRDocument).where(HRDocument.id == doc.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_young_document_is_kept(
    test_session: AsyncSession,
    retention_user: User,
    td_template: HRTemplate,
    tmp_path: Path,
) -> None:
    """Document younger than 30 days is left untouched."""
    doc_file = tmp_path / "young_doc.docx"
    doc_file.write_bytes(MINIMAL_DOCX)

    now = datetime.now(UTC)
    young_date = now - timedelta(days=1)

    doc = HRDocument(
        file_id="young123",
        template_id=td_template.id,
        template_name="td_osnovnoy.docx",
        employee_name="Test Employee",
        file_path=str(doc_file),
        file_size=len(MINIMAL_DOCX),
        created_by=retention_user.id,
        created_at=young_date,
    )
    test_session.add(doc)
    await test_session.commit()
    await test_session.refresh(doc)

    deleted = await cleanup_old_documents(test_session, now, retention_days=30)
    await test_session.commit()

    assert deleted == 0
    assert doc_file.exists()

    result = await test_session.execute(
        select(HRDocument).where(HRDocument.id == doc.id)
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_td_osnovnoy_old_document_also_deleted(
    test_session: AsyncSession,
    retention_user: User,
    td_template: HRTemplate,
    tmp_path: Path,
) -> None:
    """Even 'important' category td_osnovnoy is deleted when statutory is empty.

    This test locks the intentional behaviour so a future refactor does
    not accidentally skip it "out of kindness".
    """
    doc_file = tmp_path / "td_old.docx"
    doc_file.write_bytes(MINIMAL_DOCX)

    now = datetime.now(UTC)
    old_date = now - timedelta(days=35)

    doc = HRDocument(
        file_id="td_old123",
        template_id=td_template.id,
        template_name="td_osnovnoy.docx",
        employee_name="Important Employee",
        file_path=str(doc_file),
        file_size=len(MINIMAL_DOCX),
        created_by=retention_user.id,
        created_at=old_date,
    )
    test_session.add(doc)
    await test_session.commit()
    await test_session.refresh(doc)

    deleted = await cleanup_old_documents(test_session, now, retention_days=30)
    await test_session.commit()

    assert deleted == 1
    assert not doc_file.exists()

    result = await test_session.execute(
        select(HRDocument).where(HRDocument.id == doc.id)
    )
    assert result.scalar_one_or_none() is None
