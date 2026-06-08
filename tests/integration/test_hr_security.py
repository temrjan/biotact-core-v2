"""Integration tests for HR module security (PR-1 + PR-2).

Verifies that:
- HR endpoints require both authentication AND email in HR_ALLOWED_EMAILS.
- Empty allowlist denies everyone (fail-closed).
- download_rendered returns 404 for non-existent file_id (IDOR closure, PR-2).
"""

import os
from collections.abc import Generator

import pytest
from httpx import AsyncClient

from biotact.core.config import Settings, get_settings
from biotact.main import app

# HR models use PostgreSQL JSONB columns (extracted_styles, template_fields)
# which SQLite cannot render. CI sets DATABASE_URL to a Postgres service;
# locally we skip these tests unless the same is provided.
pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="HR module uses JSONB columns; requires PostgreSQL (set DATABASE_URL)",
)


def _build_settings(allowed_emails: str) -> Settings:
    """Build a Settings instance with a specific HR allowlist (testing-only)."""
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
def hr_empty_allowlist() -> Generator[None, None, None]:
    """Override settings with an empty HR allowlist (fail-closed)."""
    app.dependency_overrides[get_settings] = lambda: _build_settings("")
    yield


HR_READ_ENDPOINTS = [
    "/api/v1/hr/library",
    "/api/v1/hr/documents",
    "/api/v1/hr/documents/download/nonexistent_file_id",
]


@pytest.mark.integration
class TestHrAuthorization:
    """Tests for HR endpoint authorization (PR-1 RequireHREmailDep)."""

    @pytest.mark.parametrize("path", HR_READ_ENDPOINTS)
    async def test_unauthenticated_request_rejected(
        self,
        async_client: AsyncClient,
        path: str,
    ) -> None:
        """No Authorization header → 401 or 403 (depending on HTTPBearer)."""
        response = await async_client.get(path)
        assert response.status_code in (401, 403)

    @pytest.mark.parametrize("path", HR_READ_ENDPOINTS)
    async def test_authed_user_not_in_allowlist_gets_403(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        hr_empty_allowlist: None,
        path: str,
    ) -> None:
        """Authenticated user with email NOT in allowlist → 403 fail-closed."""
        response = await async_client.get(path, headers=auth_headers)
        assert response.status_code == 403

    async def test_hr_user_can_list_library(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        hr_allow_test_user: None,
    ) -> None:
        """User in allowlist → GET /hr/library returns 200 with list shape."""
        response = await async_client.get("/api/v1/hr/library", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data


@pytest.mark.integration
class TestHrDocumentIdorClosure:
    """Tests for IDOR closure on /hr/documents/download/{file_id} (PR-2)."""

    async def test_nonexistent_file_id_returns_404(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        hr_allow_test_user: None,
    ) -> None:
        """HR user requests download with file_id not in DB → 404, not 500/200."""
        response = await async_client.get(
            "/api/v1/hr/documents/download/abcdef123456",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "detail" in response.json()
