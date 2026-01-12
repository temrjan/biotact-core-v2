"""Tests for DashboardService."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from biotact.modules.command.base import ToolCall
from biotact.modules.dashboard.config import dashboard_config
from biotact.modules.dashboard.service import DashboardService
from biotact.schemas.dashboard import (
    Category,
    TransactionType,
)


@pytest.fixture
def mock_dashboard_repo() -> MagicMock:
    """Create mock DashboardRepository."""
    repo = MagicMock()

    # Mock transaction
    mock_transaction = MagicMock()
    mock_transaction.id = 1
    mock_transaction.transaction_id = "txn_abc123"
    mock_transaction.type = "expense"
    mock_transaction.amount = Decimal("15000000")
    mock_transaction.category = "hosting"
    mock_transaction.period = "monthly"
    mock_transaction.description = "Server costs"
    mock_transaction.transaction_date = date.today()
    mock_transaction.created_at = date.today()
    mock_transaction.user_id = 1

    repo.create_transaction = AsyncMock(return_value=mock_transaction)
    repo.get_transaction_by_id = AsyncMock(return_value=mock_transaction)
    repo.get_transactions = AsyncMock(return_value=([mock_transaction], 1))
    repo.get_totals_by_type = AsyncMock(
        return_value={
            "income": Decimal("50000000"),
            "expense": Decimal("30000000"),
        }
    )
    repo.get_totals_by_category = AsyncMock(
        return_value={
            "hosting": Decimal("15000000"),
            "marketing": Decimal("10000000"),
            "salary": Decimal("5000000"),
        }
    )
    repo.delete_transaction = AsyncMock(return_value=True)

    return repo


@pytest.fixture
def dashboard_service(mock_dashboard_repo: MagicMock) -> DashboardService:
    """Create DashboardService with mocked repository."""
    return DashboardService(
        config=dashboard_config,
        repository=mock_dashboard_repo,
    )


class TestDashboardServiceContext:
    """Tests for DashboardService.get_context method."""

    @pytest.mark.unit
    def test_get_context_returns_categories(
        self, dashboard_service: DashboardService
    ) -> None:
        """get_context should return categories list."""
        context = dashboard_service.get_context()

        assert "categories" in context
        assert "hosting" in context["categories"]
        assert "marketing" in context["categories"]

    @pytest.mark.unit
    def test_get_context_returns_current_date(
        self, dashboard_service: DashboardService
    ) -> None:
        """get_context should return current date."""
        context = dashboard_service.get_context()

        assert "current_date" in context
        assert context["current_date"] == date.today().isoformat()


class TestDashboardServiceExecuteTool:
    """Tests for DashboardService.execute_tool method."""

    @pytest.mark.unit
    async def test_execute_tool_add_record_success(
        self, dashboard_service: DashboardService
    ) -> None:
        """execute_tool should handle add_financial_record successfully."""
        tool_call = ToolCall(
            name="add_financial_record",
            arguments={
                "type": "expense",
                "amount": 15000000,
                "category": "hosting",
                "period": "monthly",
                "description": "Server costs",
            },
            raw_arguments="{}",
        )

        result = await dashboard_service.execute_tool(tool_call)

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "expense"
        assert result.data["amount"] == 15000000
        assert result.data["category"] == "hosting"

    @pytest.mark.unit
    async def test_execute_tool_add_record_missing_type(
        self, dashboard_service: DashboardService
    ) -> None:
        """execute_tool should return error for missing type."""
        tool_call = ToolCall(
            name="add_financial_record",
            arguments={
                "amount": 15000000,
                "category": "hosting",
            },
            raw_arguments="{}",
        )

        result = await dashboard_service.execute_tool(tool_call)

        assert result.success is False
        assert result.needs_clarification is True

    @pytest.mark.unit
    async def test_execute_tool_add_record_invalid_category(
        self, dashboard_service: DashboardService
    ) -> None:
        """execute_tool should return error for invalid category."""
        tool_call = ToolCall(
            name="add_financial_record",
            arguments={
                "type": "expense",
                "amount": 15000000,
                "category": "invalid_category",
            },
            raw_arguments="{}",
        )

        result = await dashboard_service.execute_tool(tool_call)

        assert result.success is False
        assert "invalid_category" in result.message.lower() or "категория" in result.message.lower()

    @pytest.mark.unit
    async def test_execute_tool_get_report_success(
        self, dashboard_service: DashboardService
    ) -> None:
        """execute_tool should handle get_financial_report successfully."""
        tool_call = ToolCall(
            name="get_financial_report",
            arguments={"period": "monthly"},
            raw_arguments="{}",
        )

        result = await dashboard_service.execute_tool(tool_call)

        assert result.success is True
        assert result.data is not None
        assert result.data["action"] == "get_report"

    @pytest.mark.unit
    async def test_execute_tool_unknown_tool(
        self, dashboard_service: DashboardService
    ) -> None:
        """execute_tool should return error for unknown tool."""
        tool_call = ToolCall(
            name="unknown_tool",
            arguments={},
            raw_arguments="{}",
        )

        result = await dashboard_service.execute_tool(tool_call)

        assert result.success is False
        assert "unknown_tool" in result.message.lower() or "неизвестн" in result.message.lower()


class TestDashboardServiceAddTransaction:
    """Tests for DashboardService.add_transaction method."""

    @pytest.mark.unit
    async def test_add_transaction_creates_record(
        self,
        dashboard_service: DashboardService,
        mock_dashboard_repo: MagicMock,
    ) -> None:
        """add_transaction should create transaction in repository."""
        result = await dashboard_service.add_transaction(
            user_id=1,
            type_="expense",
            amount=Decimal("15000000"),
            category="hosting",
            period="monthly",
            description="Server costs",
        )

        mock_dashboard_repo.create_transaction.assert_called_once()
        assert result.type == TransactionType.EXPENSE
        assert result.category == Category.HOSTING

    @pytest.mark.unit
    async def test_add_transaction_returns_response(
        self, dashboard_service: DashboardService
    ) -> None:
        """add_transaction should return TransactionResponse."""
        result = await dashboard_service.add_transaction(
            user_id=1,
            type_="income",
            amount=Decimal("50000000"),
            category="sales",
        )

        assert result.transaction_id == "txn_abc123"
        assert result.id == 1


class TestDashboardServiceGetReport:
    """Tests for DashboardService.get_report method."""

    @pytest.mark.unit
    async def test_get_report_returns_totals(
        self, dashboard_service: DashboardService
    ) -> None:
        """get_report should return income and expense totals."""
        result = await dashboard_service.get_report(user_id=1)

        assert result.total_income == Decimal("50000000")
        assert result.total_expenses == Decimal("30000000")
        assert result.net_balance == Decimal("20000000")

    @pytest.mark.unit
    async def test_get_report_calculates_profit_margin(
        self, dashboard_service: DashboardService
    ) -> None:
        """get_report should calculate profit margin."""
        result = await dashboard_service.get_report(user_id=1)

        # Profit margin formula: (net_balance / total_income) * 100 = 40%
        assert result.profit_margin is not None
        assert abs(result.profit_margin - 40.0) < 0.01

    @pytest.mark.unit
    async def test_get_report_includes_category_breakdown(
        self, dashboard_service: DashboardService
    ) -> None:
        """get_report should include breakdown by category."""
        result = await dashboard_service.get_report(user_id=1)

        assert len(result.by_category) == 3
        categories = {c.category for c in result.by_category}
        assert Category.HOSTING in categories
        assert Category.MARKETING in categories

    @pytest.mark.unit
    async def test_get_report_includes_transactions(
        self, dashboard_service: DashboardService
    ) -> None:
        """get_report should include recent transactions."""
        result = await dashboard_service.get_report(user_id=1)

        assert len(result.transactions) == 1
        assert result.transactions[0].transaction_id == "txn_abc123"

    @pytest.mark.unit
    async def test_get_report_with_date_filter(
        self,
        dashboard_service: DashboardService,
        mock_dashboard_repo: MagicMock,
    ) -> None:
        """get_report should pass date filters to repository."""
        start = date(2026, 1, 1)
        end = date(2026, 1, 31)

        await dashboard_service.get_report(
            user_id=1,
            start_date=start,
            end_date=end,
        )

        mock_dashboard_repo.get_totals_by_type.assert_called_once_with(
            user_id=1,
            start_date=start,
            end_date=end,
        )


class TestDashboardServiceFormatAmount:
    """Tests for DashboardService._format_amount method."""

    @pytest.mark.unit
    def test_format_amount_with_millions(
        self, dashboard_service: DashboardService
    ) -> None:
        """_format_amount should format millions with spaces."""
        result = dashboard_service._format_amount(Decimal("15000000"))
        assert result == "15 000 000"

    @pytest.mark.unit
    def test_format_amount_with_thousands(
        self, dashboard_service: DashboardService
    ) -> None:
        """_format_amount should format thousands with spaces."""
        result = dashboard_service._format_amount(Decimal("500000"))
        assert result == "500 000"

    @pytest.mark.unit
    def test_format_amount_small_number(
        self, dashboard_service: DashboardService
    ) -> None:
        """_format_amount should handle small numbers."""
        result = dashboard_service._format_amount(Decimal("100"))
        assert result == "100"
