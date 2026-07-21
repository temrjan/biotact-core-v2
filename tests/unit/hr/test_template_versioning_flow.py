"""Tests for HR template versioning flow (PR-8).

Requires PostgreSQL because HRTemplate uses JSONB columns.
"""

import asyncio
import os
from collections.abc import Generator

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from biotact.core.config import Settings, get_settings
from biotact.main import app
from biotact.modules.hr.library.models import HRTemplate
from tests.factories import make_docx_bytes

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="HR models use JSONB columns; requires PostgreSQL",
)


# Real, openable DOCX — the upload path now rejects unopenable files.
MINIMAL_DOCX = make_docx_bytes(["FIO"])


class FakeUploadFile:
    """Minimal UploadFile mock for service-layer tests."""

    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._content):
            return b""
        if size < 0:
            chunk = self._content[self._pos :]
        else:
            chunk = self._content[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


def _build_settings(allowed_emails: str) -> Settings:
    """Build a Settings instance with a specific HR allowlist (testing-only)."""
    return Settings(
        debug=False,
        secret_key="test-secret-key-for-testing-only",
        postgres_host="localhost",
        postgres_port=5432,
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
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def authenticated_client_with_hr(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> AsyncClient:
    """Authenticated client with HR allowlist override applied."""
    return authenticated_client


@pytest.mark.asyncio
async def test_upload_bumps_version_and_deactivates_previous(
    authenticated_client_with_hr: AsyncClient,
    test_user: None,
    test_session: AsyncSession,
) -> None:
    """Second upload in the same category bumps version and deactivates prev."""
    category = "трудовой_договор_flow"

    r1 = await authenticated_client_with_hr.post(
        "/api/v1/hr/library",
        params={"category": category},
        files={"file": ("v1.docx", MINIMAL_DOCX, "application/octet-stream")},
    )
    assert r1.status_code == 201
    v1 = r1.json()
    assert v1["version"] == 1
    assert v1["is_active"] is True
    assert v1["superseded_by_id"] is None

    r2 = await authenticated_client_with_hr.post(
        "/api/v1/hr/library",
        params={"category": category},
        files={"file": ("v2.docx", MINIMAL_DOCX, "application/octet-stream")},
    )
    assert r2.status_code == 201
    v2 = r2.json()
    assert v2["version"] == 2
    assert v2["is_active"] is True
    assert v2["superseded_by_id"] is None

    # Previous is now inactive and points to v2.
    result = await test_session.execute(
        select(HRTemplate).where(HRTemplate.id == v1["id"])
    )
    prev = result.scalar_one()
    assert prev.is_active is False
    assert prev.superseded_by_id == v2["id"]


@pytest.mark.asyncio
async def test_concurrent_upload_race_returns_conflict(
    test_engine: AsyncEngine,
    test_user: None,
) -> None:
    """Two parallel upload_template calls: one succeeds, one gets 409 Conflict."""
    from biotact.modules.hr.library.service import (
        HRTemplateConflictError,
        upload_template,
    )

    category = "трудовой_договор_race"

    async def _upload(name: str, session: AsyncSession) -> int:
        fake = FakeUploadFile(name, MINIMAL_DOCX)
        try:
            async with session.begin():
                await upload_template(session, fake, category, test_user.id)
        except HRTemplateConflictError:
            return 409
        else:
            return 201

    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as s1, async_session() as s2:
        statuses = await asyncio.gather(
            _upload("a.docx", s1),
            _upload("b.docx", s2),
        )

    assert sorted(statuses) == [201, 409]


@pytest.mark.asyncio
async def test_rollback_makes_target_active(
    authenticated_client_with_hr: AsyncClient,
    test_user: None,
    test_session: AsyncSession,
) -> None:
    """Rollback reactivates an older version and deactivates current."""
    category = "трудовой_договор_rollback"

    r1 = await authenticated_client_with_hr.post(
        "/api/v1/hr/library",
        params={"category": category},
        files={"file": ("v1.docx", MINIMAL_DOCX, "application/octet-stream")},
    )
    v1 = r1.json()

    r2 = await authenticated_client_with_hr.post(
        "/api/v1/hr/library",
        params={"category": category},
        files={"file": ("v2.docx", MINIMAL_DOCX, "application/octet-stream")},
    )
    v2 = r2.json()
    assert v2["version"] == 2
    assert v2["is_active"] is True

    rollback = await authenticated_client_with_hr.post(
        f"/api/v1/hr/library/{v1['id']}/rollback"
    )
    assert rollback.status_code == 200
    data = rollback.json()
    assert data["id"] == v1["id"]
    assert data["is_active"] is True
    assert data["version"] == 1

    result = await test_session.execute(
        select(HRTemplate).where(HRTemplate.id == v2["id"])
    )
    current = result.scalar_one()
    assert current.is_active is False
    assert current.superseded_by_id == v1["id"]


@pytest.mark.asyncio
async def test_get_template_by_category_returns_only_active(
    authenticated_client_with_hr: AsyncClient,
    test_user: None,
    test_session: AsyncSession,
) -> None:
    """get_template_by_category ignores inactive superseded templates."""
    from biotact.modules.hr.library.service import get_template_by_category

    category = "трудовой_договор_active"

    r1 = await authenticated_client_with_hr.post(
        "/api/v1/hr/library",
        params={"category": category},
        files={"file": ("v1.docx", MINIMAL_DOCX, "application/octet-stream")},
    )
    v1 = r1.json()

    r2 = await authenticated_client_with_hr.post(
        "/api/v1/hr/library",
        params={"category": category},
        files={"file": ("v2.docx", MINIMAL_DOCX, "application/octet-stream")},
    )
    v2 = r2.json()

    # get_template_by_category now gates on render-eligibility (template_fields
    # IS NOT NULL), not extracted_text — extraction is unrelated to rendering.
    # The fake-docx rows carry no placeholders, so backfill template_fields.
    await test_session.execute(
        update(HRTemplate)
        .where(HRTemplate.category == category)
        .values(template_fields=["FIELD"])
    )
    await test_session.commit()

    # Direct service call should return only v2 (active).
    active = await get_template_by_category(test_session, category)
    assert active is not None
    assert active.id == v2["id"]
    assert active.id != v1["id"]


@pytest.mark.asyncio
async def test_list_template_history(
    authenticated_client_with_hr: AsyncClient,
    test_user: None,
) -> None:
    """History endpoint returns all versions ordered newest first."""
    category = "трудовой_договор_history"

    r1 = await authenticated_client_with_hr.post(
        "/api/v1/hr/library",
        params={"category": category},
        files={"file": ("v1.docx", MINIMAL_DOCX, "application/octet-stream")},
    )
    v1 = r1.json()

    r2 = await authenticated_client_with_hr.post(
        "/api/v1/hr/library",
        params={"category": category},
        files={"file": ("v2.docx", MINIMAL_DOCX, "application/octet-stream")},
    )
    v2 = r2.json()

    response = await authenticated_client_with_hr.get(
        f"/api/v1/hr/library/{category}/history"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["id"] == v2["id"]
    assert data["items"][0]["version"] == 2
    assert data["items"][1]["id"] == v1["id"]
    assert data["items"][1]["version"] == 1


@pytest.mark.asyncio
async def test_rollback_not_found(
    authenticated_client_with_hr: AsyncClient,
    test_user: None,
) -> None:
    """Rollback to a non-existent template returns 404."""
    response = await authenticated_client_with_hr.post(
        "/api/v1/hr/library/999999/rollback"
    )
    assert response.status_code == 404
