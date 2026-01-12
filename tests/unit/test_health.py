"""Tests for health check endpoint."""

import pytest
from fastapi.testclient import TestClient

from biotact import __version__


@pytest.mark.unit
def test_health_check_returns_healthy(client: TestClient) -> None:
    """Health endpoint should return healthy status."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert data["version"] == __version__
    assert "timestamp" in data
    assert "dependencies" in data


@pytest.mark.unit
def test_root_endpoint(client: TestClient) -> None:
    """Root endpoint should return service info."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Biotact Platform"
    assert data["version"] == __version__
    assert data["docs"] == "/docs"
