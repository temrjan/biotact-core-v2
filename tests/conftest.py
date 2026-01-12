"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from biotact.core.config import Settings
from biotact.core.database import Base, get_session
from biotact.core.dependencies import (
    get_embedding_service,
    get_llm_service,
    get_qdrant_service,
)
from biotact.core.security import create_access_token, hash_password
from biotact.main import app
from biotact.models.user import User

# =============================================================================
# Test Settings
# =============================================================================


def get_test_settings() -> Settings:
    """Get settings for testing."""
    return Settings(
        app_env="testing",
        debug=False,
        secret_key="test-secret-key-for-testing-only",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_user="biotact",
        postgres_password="biotact_test",
        postgres_db="biotact_test",
        openai_api_key="sk-test-key",
    )


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create test database engine with SQLite in-memory."""
    # Use SQLite for fast integration tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Enable foreign keys for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn: Any, _connection_record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(
    test_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session() as session:
        yield session


# =============================================================================
# User Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def test_user(test_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="test@biotact.uz",
        hashed_password=hash_password("testpassword123"),
        full_name="Test User",
        department_id="marketing",
        is_active=True,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_dashboard(test_session: AsyncSession) -> User:
    """Create a test user for dashboard department."""
    user = User(
        email="dashboard@biotact.uz",
        hashed_password=hash_password("testpassword123"),
        full_name="Dashboard User",
        department_id="dashboard",
        is_active=True,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user: User) -> str:
    """Create authentication token for test user."""
    return create_access_token({"sub": str(test_user.id)})


@pytest.fixture
def auth_token_dashboard(test_user_dashboard: User) -> str:
    """Create authentication token for dashboard user."""
    return create_access_token({"sub": str(test_user_dashboard.id)})


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    """Create authorization headers."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def auth_headers_dashboard(auth_token_dashboard: str) -> dict[str, str]:
    """Create authorization headers for dashboard user."""
    return {"Authorization": f"Bearer {auth_token_dashboard}"}


# =============================================================================
# Mock RAG Services
# =============================================================================


def create_mock_embedding_service() -> MagicMock:
    """Create mock embedding service."""
    mock = MagicMock()
    mock.embed_text = AsyncMock(return_value=[0.1] * 3072)  # text-embedding-3-large
    return mock


def create_mock_qdrant_service() -> MagicMock:
    """Create mock Qdrant service."""
    mock = MagicMock()
    mock.search = AsyncMock(return_value=[])
    mock.search_all_departments = AsyncMock(return_value=[])
    mock.health_check = AsyncMock(return_value=True)
    return mock


def create_mock_llm_service() -> MagicMock:
    """Create mock LLM service."""
    mock = MagicMock()
    mock.generate_response = AsyncMock(return_value="Test response from LLM")
    mock.generate_title = AsyncMock(return_value="Test Chat Session")
    return mock


# =============================================================================
# HTTP Client Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def async_client(
    test_engine: AsyncEngine,
    test_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client with test database and mocked services."""

    # Override the session dependency
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    # Create mock RAG services
    mock_embedding = create_mock_embedding_service()
    mock_qdrant = create_mock_qdrant_service()
    mock_llm = create_mock_llm_service()

    # Override all dependencies
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_embedding_service] = lambda: mock_embedding
    app.dependency_overrides[get_qdrant_service] = lambda: mock_qdrant
    app.dependency_overrides[get_llm_service] = lambda: mock_llm

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clear overrides
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authenticated_client(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> AsyncClient:
    """Create authenticated async HTTP client."""
    async_client.headers.update(auth_headers)
    return async_client


# =============================================================================
# Sync Client Fixture (for simple unit tests)
# =============================================================================


@pytest.fixture
def client() -> TestClient:
    """Create sync TestClient for simple endpoint tests."""
    return TestClient(app)
