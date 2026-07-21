"""Tests for HR template file download (PR-1).

Requires PostgreSQL because HRTemplate uses JSONB columns.
"""

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import Settings, get_settings
from biotact.main import app
from biotact.models.user import User
from biotact.modules.hr.library.models import HRTemplate

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="HR models use JSONB columns; requires PostgreSQL",
)

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
MINIMAL_DOCX = b"PK\x03\x04" + b"\x00" * 200


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
def hr_deny_all() -> Generator[None, None, None]:
    """Override settings with an empty HR allowlist — nobody has HR access."""
    app.dependency_overrides[get_settings] = lambda: _build_settings("")
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def authenticated_client_with_hr(
    authenticated_client: AsyncClient,
    hr_allow_test_user: None,
) -> AsyncClient:
    """Authenticated client whose user is in the HR allowlist."""
    return authenticated_client


async def _upload_template(client: AsyncClient, category: str) -> dict[str, Any]:
    """Upload a minimal DOCX template and return the created record."""
    response = await client.post(
        "/api/v1/hr/library",
        params={"category": category},
        files={"file": ("tpl.docx", MINIMAL_DOCX, "application/octet-stream")},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_download_returns_file_bytes(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
) -> None:
    """Download returns the raw docx bytes with an attachment filename."""
    tpl = await _upload_template(authenticated_client_with_hr, "договор_download")

    response = await authenticated_client_with_hr.get(
        f"/api/v1/hr/library/{tpl['id']}/download"
    )

    assert response.status_code == 200
    assert response.content == MINIMAL_DOCX
    assert response.headers["content-type"] == DOCX_MEDIA_TYPE
    assert "tpl.docx" in response.headers["content-disposition"]


@pytest.mark.parametrize(
    ("suffix", "content", "expected_media_type"),
    [
        ("pdf", b"%PDF-1.4\n" + b"\x00" * 100, "application/pdf"),
        ("txt", b"plain text sample", "text/plain"),
        ("md", b"# heading\n", "text/markdown"),
    ],
)
@pytest.mark.asyncio
async def test_download_sets_media_type_per_file_type(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
    suffix: str,
    content: bytes,
    expected_media_type: str,
) -> None:
    """Non-docx templates download with the media type mapped from file_type."""
    response = await authenticated_client_with_hr.post(
        "/api/v1/hr/library",
        params={"category": f"договор_media_{suffix}"},
        files={"file": (f"tpl.{suffix}", content, "application/octet-stream")},
    )
    assert response.status_code == 201
    template_id = response.json()["id"]

    download = await authenticated_client_with_hr.get(
        f"/api/v1/hr/library/{template_id}/download"
    )

    assert download.status_code == 200
    assert download.content == content
    # Starlette appends "; charset=utf-8" to text/* types — compare the type only.
    assert download.headers["content-type"].split(";")[0] == expected_media_type


@pytest.mark.asyncio
async def test_download_unknown_id_returns_404(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
) -> None:
    """Download of a non-existent template id returns 404."""
    response = await authenticated_client_with_hr.get(
        "/api/v1/hr/library/999999/download"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_missing_file_on_disk_returns_404(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
    test_session: AsyncSession,
) -> None:
    """Row exists but the file was removed from disk → 404, not 500 (F2)."""
    tpl = await _upload_template(authenticated_client_with_hr, "договор_missing")

    result = await test_session.execute(
        select(HRTemplate).where(HRTemplate.id == tpl["id"])
    )
    Path(result.scalar_one().file_path).unlink()

    response = await authenticated_client_with_hr.get(
        f"/api/v1/hr/library/{tpl['id']}/download"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_rejects_invalid_token(async_client: AsyncClient) -> None:
    """A present-but-invalid Bearer token → 401 (get_current_user path)."""
    response = await async_client.get(
        "/api/v1/hr/library/1/download",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_download_requires_hr_role(
    authenticated_client: AsyncClient,
    hr_deny_all: None,
    test_user: User,
) -> None:
    """Authenticated user not in the HR allowlist → 403."""
    response = await authenticated_client.get("/api/v1/hr/library/1/download")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_download_route_not_shadowed_by_history(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
) -> None:
    """`/{id}/download` resolves to download, not `/{category}/history` (F6)."""
    tpl = await _upload_template(authenticated_client_with_hr, "договор_route")

    response = await authenticated_client_with_hr.get(
        f"/api/v1/hr/library/{tpl['id']}/download"
    )

    # history route returns JSON {items: [...]}; download returns a binary docx
    assert response.status_code == 200
    assert response.headers["content-type"] == DOCX_MEDIA_TYPE
