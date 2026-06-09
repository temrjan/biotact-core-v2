"""Integration tests for HR template versioning end-to-end (PR-11)."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from biotact.core.config import Settings, get_settings
from biotact.main import app

if TYPE_CHECKING:
    from collections.abc import Generator

    from httpx import AsyncClient

pytestmark = pytest.mark.integration

MINIMAL_DOCX = b"PK\x03\x04" + b"\x00" * 200


def _hr_settings() -> Settings:
    """Override settings so test@biotact.uz is HR-allowed."""
    return Settings(
        app_env="development",
        debug=False,
        secret_key="test-secret-key-for-testing-only",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_user="biotact",
        postgres_password="biotact_test",
        postgres_db="biotact_test",
        openai_api_key="sk-test-key",
        hr_allowed_emails="test@biotact.uz",
    )


@pytest.fixture
def hr_allow() -> Generator[None, None, None]:
    app.dependency_overrides[get_settings] = _hr_settings
    yield
    app.dependency_overrides.pop(get_settings, None)


@pytest_asyncio.fixture
async def hr_client(
    authenticated_client: AsyncClient,
    hr_allow: None,
) -> AsyncClient:
    return authenticated_client


class TestVersioningEndToEnd:
    """v1 → v2 → rollback via HTTP API."""

    @pytest.mark.asyncio
    async def test_upload_v1_and_v2_creates_history(self, hr_client: AsyncClient) -> None:
        """Upload two versions and verify history lists both."""
        files = {"file": ("v1.docx", BytesIO(MINIMAL_DOCX), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        r1 = await hr_client.post("/api/v1/hr/library?category=td_test", files=files)
        assert r1.status_code == 201
        v1_id = r1.json()["id"]

        files = {"file": ("v2.docx", BytesIO(MINIMAL_DOCX), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        r2 = await hr_client.post("/api/v1/hr/library?category=td_test", files=files)
        assert r2.status_code == 201
        v2_id = r2.json()["id"]

        hist = await hr_client.get("/api/v1/hr/library/td_test/history")
        assert hist.status_code == 200
        items = hist.json()["items"]
        assert len(items) == 2
        assert items[0]["version"] == 2
        assert items[1]["version"] == 1

        return v1_id, v2_id

    @pytest.mark.asyncio
    async def test_rollback_makes_v1_active(self, hr_client: AsyncClient) -> None:
        """Upload v1, v2, rollback to v1, assert v1 active."""
        files = {"file": ("v1.docx", BytesIO(MINIMAL_DOCX), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        r1 = await hr_client.post("/api/v1/hr/library?category=td_test_rollback", files=files)
        assert r1.status_code == 201
        v1_id = r1.json()["id"]

        files = {"file": ("v2.docx", BytesIO(MINIMAL_DOCX), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        r2 = await hr_client.post("/api/v1/hr/library?category=td_test_rollback", files=files)
        assert r2.status_code == 201

        rb = await hr_client.post(f"/api/v1/hr/library/{v1_id}/rollback")
        assert rb.status_code == 200
        assert rb.json()["is_active"] is True
        assert rb.json()["version"] == 1

        detail = await hr_client.get(f"/api/v1/hr/library/{v1_id}")
        assert detail.status_code == 200
        assert detail.json()["is_active"] is True
