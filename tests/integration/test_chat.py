"""Integration tests for chat endpoints."""

import pytest
from httpx import AsyncClient

from biotact.models.user import User


@pytest.mark.integration
class TestChatQuery:
    """Tests for POST /api/v1/chat/query endpoint."""

    async def test_chat_query_unauthorized(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test chat query without authentication."""
        response = await async_client.post(
            "/api/v1/chat/query",
            json={"message": "Hello"},
        )

        assert response.status_code == 401

    async def test_chat_query_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test successful chat query with mocked services."""
        response = await authenticated_client.post(
            "/api/v1/chat/query",
            json={"message": "What is Biotact?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "session_id" in data
        assert data["answer"] == "Test response from LLM"

    async def test_chat_query_with_session_id(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test chat query with existing session ID."""
        # First message
        response1 = await authenticated_client.post(
            "/api/v1/chat/query",
            json={"message": "Hello"},
        )
        assert response1.status_code == 200
        session_id = response1.json()["session_id"]

        # Second message in same session
        response2 = await authenticated_client.post(
            "/api/v1/chat/query",
            json={
                "message": "Follow up question",
                "session_id": session_id,
            },
        )
        assert response2.status_code == 200
        assert response2.json()["session_id"] == session_id

    async def test_chat_query_validation_empty_message(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """Test chat query with empty message."""
        response = await authenticated_client.post(
            "/api/v1/chat/query",
            json={"message": ""},
        )

        assert response.status_code == 422

    async def test_chat_query_validation_message_too_long(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """Test chat query with message exceeding max length."""
        long_message = "x" * 5000  # Exceeds 4000 char limit

        response = await authenticated_client.post(
            "/api/v1/chat/query",
            json={"message": long_message},
        )

        assert response.status_code == 422


@pytest.mark.integration
class TestChatSessions:
    """Tests for GET /api/v1/chat/sessions endpoint."""

    async def test_get_sessions_unauthorized(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test getting sessions without authentication."""
        response = await async_client.get("/api/v1/chat/sessions")

        assert response.status_code == 401

    async def test_get_sessions_empty(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test getting sessions when user has no sessions."""
        response = await authenticated_client.get("/api/v1/chat/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["sessions"] == []

    async def test_get_sessions_with_data(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test getting sessions after creating some chat sessions."""
        # Create a few chat sessions
        for i in range(3):
            await authenticated_client.post(
                "/api/v1/chat/query",
                json={"message": f"Question {i}"},
            )

        response = await authenticated_client.get("/api/v1/chat/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["sessions"]) == 3

    async def test_get_sessions_pagination(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test sessions pagination."""
        # Create 5 chat sessions
        for i in range(5):
            await authenticated_client.post(
                "/api/v1/chat/query",
                json={"message": f"Question {i}"},
            )

        # Get with limit
        response = await authenticated_client.get(
            "/api/v1/chat/sessions?limit=2&offset=0"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 2

        # Get with offset
        response = await authenticated_client.get(
            "/api/v1/chat/sessions?limit=2&offset=2"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 2
