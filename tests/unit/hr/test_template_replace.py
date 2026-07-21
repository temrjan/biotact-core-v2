"""Tests for HR safe template replace (PR-2): corrupt-guard + dropped-fields confirm.

Requires PostgreSQL because HRTemplate uses JSONB columns.
"""

import os
from collections.abc import Generator, Sequence

import pytest
from httpx import AsyncClient, Response

from biotact.core.config import Settings, get_settings
from biotact.main import app
from biotact.models.user import User
from tests.factories import make_docx_bytes

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="HR models use JSONB columns; requires PostgreSQL",
)


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
    """Authenticated client whose user is in the HR allowlist."""
    return authenticated_client


async def _upload(
    client: AsyncClient,
    category: str,
    *,
    fields: Sequence[str] = ("FIO",),
    confirm: bool | None = None,
    content: bytes | None = None,
) -> Response:
    """Upload a template (real DOCX with `fields` unless `content` overrides)."""
    params: dict[str, object] = {"category": category}
    if confirm is not None:
        params["confirm"] = str(confirm).lower()
    body = content if content is not None else make_docx_bytes(fields)
    return await client.post(
        "/api/v1/hr/library",
        params=params,
        files={"file": ("tpl.docx", body, "application/octet-stream")},
    )


@pytest.mark.asyncio
async def test_corrupt_docx_rejected(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
) -> None:
    """A file that passes magic bytes but isn't a real DOCX → 422 (not silently stored)."""
    response = await _upload(
        authenticated_client_with_hr,
        "договор_corrupt",
        content=b"PK\x03\x04" + b"\x00" * 200,  # ZIP magic, but not a DOCX package
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_first_upload_needs_no_confirm(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
) -> None:
    """First upload to a fresh category has no previous version → no confirm needed."""
    response = await _upload(
        authenticated_client_with_hr, "договор_first", fields=["FIO", "DATE"]
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_replace_dropping_field_requires_confirm(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
) -> None:
    """Replacement losing a placeholder → 409 with the dropped list, no confirm."""
    category = "договор_drop"
    first = await _upload(
        authenticated_client_with_hr, category, fields=["FIO", "DATE", "DIRECTOR"]
    )
    assert first.status_code == 201

    response = await _upload(
        authenticated_client_with_hr, category, fields=["FIO", "DATE"]
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "dropped_placeholders"
    assert "DIRECTOR" in detail["dropped"]


@pytest.mark.asyncio
async def test_replace_with_confirm_succeeds(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
) -> None:
    """With confirm=true the field-drop is accepted and a new version is created."""
    category = "договор_drop_confirm"
    first = await _upload(
        authenticated_client_with_hr, category, fields=["FIO", "DIRECTOR"]
    )
    assert first.status_code == 201

    response = await _upload(
        authenticated_client_with_hr, category, fields=["FIO"], confirm=True
    )
    assert response.status_code == 201
    assert response.json()["version"] == 2


@pytest.mark.asyncio
async def test_replace_adding_field_succeeds(
    authenticated_client_with_hr: AsyncClient,
    test_user: User,
) -> None:
    """Replacement that only adds placeholders drops nothing → 201 without confirm."""
    category = "договор_add"
    first = await _upload(authenticated_client_with_hr, category, fields=["FIO"])
    assert first.status_code == 201

    response = await _upload(
        authenticated_client_with_hr, category, fields=["FIO", "DATE"]
    )
    assert response.status_code == 201
