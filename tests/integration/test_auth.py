"""Integration tests for authentication endpoints."""

import pytest
from httpx import AsyncClient

from biotact.models.user import User


@pytest.mark.integration
class TestAuthLogin:
    """Tests for POST /api/v1/auth/login endpoint."""

    async def test_login_success(
        self,
        async_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test successful login with valid credentials."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@biotact.uz",
                "password": "testpassword123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert data["user"]["email"] == "test@biotact.uz"
        assert data["user"]["full_name"] == "Test User"

    async def test_login_mixed_case_email(
        self,
        async_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Login is case-insensitive on email.

        Emails are stored lowercase; EmailStr keeps the local-part case
        as typed, so without schema normalization `Test@Biotact.UZ`
        would miss the exact-match lookup and fail with 401.
        """
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "Test@Biotact.UZ",
                "password": "testpassword123",
            },
        )

        assert response.status_code == 200
        assert response.json()["user"]["email"] == "test@biotact.uz"

    async def test_login_invalid_email(
        self,
        async_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test login with non-existent email."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@biotact.uz",
                "password": "testpassword123",
            },
        )

        assert response.status_code == 401
        assert "detail" in response.json()

    async def test_login_invalid_password(
        self,
        async_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test login with wrong password."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@biotact.uz",
                "password": "wrongpassword",
            },
        )

        assert response.status_code == 401
        assert "detail" in response.json()

    async def test_login_missing_fields(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test login with missing required fields."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "test@biotact.uz"},
        )

        assert response.status_code == 422  # Validation error

    async def test_login_invalid_email_format(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test login with invalid email format."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "not-an-email",
                "password": "testpassword123",
            },
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.integration
class TestAuthToken:
    """Tests for authentication token validation."""

    async def test_access_protected_endpoint_with_token(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """Test accessing protected endpoint with valid token."""
        response = await authenticated_client.get("/api/v1/chat/sessions")

        assert response.status_code == 200

    async def test_access_protected_endpoint_without_token(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test accessing protected endpoint without token."""
        response = await async_client.get("/api/v1/chat/sessions")

        assert response.status_code == 401

    async def test_access_protected_endpoint_with_invalid_token(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test accessing protected endpoint with invalid token."""
        async_client.headers["Authorization"] = "Bearer invalid-token"
        response = await async_client.get("/api/v1/chat/sessions")

        assert response.status_code == 401
