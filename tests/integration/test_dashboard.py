"""Integration tests for dashboard endpoints."""

from decimal import Decimal

import pytest
from httpx import AsyncClient

from biotact.models.user import User


@pytest.mark.integration
class TestDashboardTransactions:
    """Tests for dashboard transactions endpoints."""

    async def test_create_transaction_unauthorized(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test creating transaction without authentication."""
        response = await async_client.post(
            "/api/v1/dashboard/transactions",
            json={
                "type": "expense",
                "amount": 100.0,
                "category": "marketing",
            },
        )

        assert response.status_code == 401

    async def test_create_transaction_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test creating a new transaction."""
        response = await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={
                "type": "expense",
                "amount": 1500.50,
                "category": "marketing",
                "period": "monthly",
                "description": "Ad campaign",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "expense"
        assert Decimal(str(data["amount"])) == Decimal("1500.50")
        assert data["category"] == "marketing"
        assert data["description"] == "Ad campaign"
        assert "transaction_id" in data
        assert "id" in data

    async def test_create_income_transaction(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test creating an income transaction."""
        response = await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={
                "type": "income",
                "amount": 50000.0,
                "category": "sales",
                "description": "Product sales",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "income"
        assert data["category"] == "sales"

    async def test_create_transaction_validation_error(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """Test transaction creation with invalid data."""
        # Missing required fields
        response = await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "expense"},
        )
        assert response.status_code == 422

        # Invalid type
        response = await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={
                "type": "invalid",
                "amount": 100.0,
                "category": "marketing",
            },
        )
        assert response.status_code == 422

        # Negative amount
        response = await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={
                "type": "expense",
                "amount": -100.0,
                "category": "marketing",
            },
        )
        assert response.status_code == 422

    async def test_list_transactions_empty(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test listing transactions when empty."""
        response = await authenticated_client.get("/api/v1/dashboard/transactions")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_transactions_with_data(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test listing transactions with data."""
        # Create some transactions
        for i in range(3):
            resp = await authenticated_client.post(
                "/api/v1/dashboard/transactions",
                json={
                    "type": "expense",
                    "amount": 100.0 * (i + 1),
                    "category": "office",
                },
            )
            assert resp.status_code == 200

        response = await authenticated_client.get("/api/v1/dashboard/transactions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    async def test_list_transactions_filter_by_type(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test filtering transactions by type."""
        # Create mixed transactions
        resp1 = await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "expense", "amount": 100.0, "category": "office"},
        )
        assert resp1.status_code == 200
        resp2 = await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "income", "amount": 200.0, "category": "sales"},
        )
        assert resp2.status_code == 200

        # Filter by expense
        response = await authenticated_client.get(
            "/api/v1/dashboard/transactions?type=expense"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["type"] == "expense"

        # Filter by income
        response = await authenticated_client.get(
            "/api/v1/dashboard/transactions?type=income"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["type"] == "income"

    async def test_list_transactions_filter_by_category(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test filtering transactions by category."""
        await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "expense", "amount": 100.0, "category": "marketing"},
        )
        await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "expense", "amount": 200.0, "category": "office"},
        )

        response = await authenticated_client.get(
            "/api/v1/dashboard/transactions?category=marketing"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["category"] == "marketing"

    async def test_delete_transaction_success(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test deleting a transaction."""
        # Create transaction
        create_response = await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "expense", "amount": 100.0, "category": "office"},
        )
        transaction_id = create_response.json()["transaction_id"]

        # Delete it
        response = await authenticated_client.delete(
            f"/api/v1/dashboard/transactions/{transaction_id}"
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is True

        # Verify it's gone
        list_response = await authenticated_client.get("/api/v1/dashboard/transactions")
        assert list_response.json() == []

    async def test_delete_nonexistent_transaction(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test deleting a non-existent transaction."""
        response = await authenticated_client.delete(
            "/api/v1/dashboard/transactions/nonexistent-id"
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is False


@pytest.mark.integration
class TestDashboardReport:
    """Tests for dashboard report endpoint."""

    async def test_get_report_unauthorized(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test getting report without authentication."""
        response = await async_client.get("/api/v1/dashboard/report")
        assert response.status_code == 401

    async def test_get_report_empty(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test getting report with no transactions."""
        response = await authenticated_client.get("/api/v1/dashboard/report")

        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["total_income"])) == Decimal("0")
        assert Decimal(str(data["total_expenses"])) == Decimal("0")
        assert Decimal(str(data["net_balance"])) == Decimal("0")

    async def test_get_report_with_data(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test getting report with transactions."""
        # Create income
        await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "income", "amount": 10000.0, "category": "sales"},
        )
        # Create expenses
        await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "expense", "amount": 3000.0, "category": "marketing"},
        )
        await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "expense", "amount": 2000.0, "category": "office"},
        )

        response = await authenticated_client.get("/api/v1/dashboard/report")

        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["total_income"])) == Decimal("10000")
        assert Decimal(str(data["total_expenses"])) == Decimal("5000")
        assert Decimal(str(data["net_balance"])) == Decimal("5000")
        assert "by_category" in data


@pytest.mark.integration
class TestDashboardKPI:
    """Tests for dashboard KPI endpoint."""

    async def test_get_kpi_unauthorized(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test getting KPI without authentication."""
        response = await async_client.get("/api/v1/dashboard/kpi")
        assert response.status_code == 401

    async def test_get_kpi_empty(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test getting KPI with no transactions."""
        response = await authenticated_client.get("/api/v1/dashboard/kpi")

        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["revenue"])) == Decimal("0")
        assert Decimal(str(data["expenses"])) == Decimal("0")
        assert Decimal(str(data["profit"])) == Decimal("0")
        assert data["profit_margin"] == 0.0

    async def test_get_kpi_with_data(
        self,
        authenticated_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test getting KPI with transactions."""
        # Create income
        await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "income", "amount": 20000.0, "category": "sales"},
        )
        # Create expenses
        await authenticated_client.post(
            "/api/v1/dashboard/transactions",
            json={"type": "expense", "amount": 8000.0, "category": "office"},
        )

        response = await authenticated_client.get("/api/v1/dashboard/kpi")

        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["revenue"])) == Decimal("20000")
        assert Decimal(str(data["expenses"])) == Decimal("8000")
        assert Decimal(str(data["profit"])) == Decimal("12000")
        assert data["profit_margin"] == 60.0  # 12000/20000 * 100


@pytest.mark.integration
class TestHealthCheck:
    """Tests for health check endpoint."""

    async def test_health_check_returns_ok(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test health check endpoint returns version info."""
        response = await async_client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "timestamp" in data
        assert "dependencies" in data
