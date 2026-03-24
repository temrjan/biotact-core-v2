"""Dashboard service for financial operations."""

import contextlib
import logging
from datetime import date
from decimal import Decimal
from typing import Any

from biotact.modules.base import CommandModuleConfig
from biotact.modules.command.base import BaseCommandService, CommandResult, ToolCall
from biotact.modules.dashboard.config import CATEGORY_NAMES
from biotact.repositories.dashboard_repo import DashboardRepository
from biotact.schemas.dashboard import (
    Category,
    CategoryBreakdown,
    FinancialReportResponse,
    Period,
    TransactionResponse,
    TransactionType,
)

logger = logging.getLogger(__name__)


class DashboardService(BaseCommandService):
    """Service for Dashboard financial operations.

    Handles:
    - Adding financial records (expenses/income)
    - Generating financial reports
    - KPI calculations
    """

    def __init__(
        self,
        config: CommandModuleConfig,
        repository: DashboardRepository,
    ) -> None:
        """Initialize dashboard service.

        Args:
            config: Module configuration.
            repository: Dashboard repository for data access.
        """
        super().__init__(config)
        self.repository = repository

    def get_context(self) -> dict[str, Any]:
        """Get context data for system prompt.

        Returns:
            Context with categories and current date.
        """
        return {
            "categories": ", ".join(
                f"{cat.value} ({CATEGORY_NAMES.get(cat.value, cat.value)})"
                for cat in Category
            ),
            "current_date": date.today().isoformat(),
        }

    async def execute_tool(self, tool_call: ToolCall) -> CommandResult:
        """Execute a tool call from LLM.

        Args:
            tool_call: Parsed tool call from LLM response.

        Returns:
            CommandResult with success/failure and data.
        """
        if tool_call.name == "add_financial_record":
            return await self._add_financial_record(tool_call.arguments)
        elif tool_call.name == "get_financial_report":
            return await self._get_financial_report(tool_call.arguments)
        else:
            return CommandResult(
                success=False,
                message=f"Неизвестная команда: {tool_call.name}",
            )

    async def _add_financial_record(
        self,
        args: dict[str, Any],
    ) -> CommandResult:
        """Add a new financial record.

        Args:
            args: Arguments from LLM tool call.

        Returns:
            CommandResult with created transaction data.
        """
        try:
            # Validate required fields
            type_str = args.get("type")
            amount = args.get("amount")
            category_str = args.get("category")

            if not all([type_str, amount, category_str]):
                missing = []
                if not type_str:
                    missing.append("тип (expense/income)")
                if not amount:
                    missing.append("сумма")
                if not category_str:
                    missing.append("категория")
                return CommandResult(
                    success=False,
                    message=f"Не указаны обязательные поля: {', '.join(missing)}",
                    needs_clarification=True,
                    clarification_prompt=f"Пожалуйста, уточните: {', '.join(missing)}",
                )

            # Validate enums
            try:
                trans_type = TransactionType(str(type_str))
            except ValueError:
                return CommandResult(
                    success=False,
                    message=f"Неверный тип транзакции: {type_str}. Используйте 'expense' или 'income'",
                )

            try:
                category = Category(str(category_str))
            except ValueError:
                valid_categories = ", ".join(c.value for c in Category)
                return CommandResult(
                    success=False,
                    message=f"Неверная категория: {category_str}. Доступные: {valid_categories}",
                )

            period_str = args.get("period", "monthly")
            try:
                period = Period(period_str)
            except ValueError:
                period = Period.MONTHLY

            # Create transaction (user_id will be set by router)
            # For now, we return the data to be processed
            description = args.get("description", "")
            amount_decimal = Decimal(str(amount))

            # Format response message
            type_label = "Расход" if trans_type == TransactionType.EXPENSE else "Доход"
            category_label = CATEGORY_NAMES.get(category.value, category.value)

            return CommandResult(
                success=True,
                message=f"✓ {type_label}: {self._format_amount(amount_decimal)} — {category_label}",
                data={
                    "type": trans_type.value,
                    "amount": float(amount_decimal),
                    "category": category.value,
                    "period": period.value,
                    "description": description,
                    "action": "add_record",
                },
            )

        except Exception as e:
            logger.error(f"Error adding financial record: {e}")
            return CommandResult(
                success=False,
                message=f"Ошибка при добавлении записи: {e!s}",
            )

    async def _get_financial_report(
        self,
        args: dict[str, Any],
    ) -> CommandResult:
        """Get financial report.

        Args:
            args: Arguments from LLM tool call.

        Returns:
            CommandResult with report data.
        """
        try:
            period_str = args.get("period")
            period = None
            if period_str:
                with contextlib.suppress(ValueError):
                    period = Period(period_str)

            # Return data to be processed with user context
            return CommandResult(
                success=True,
                message="Формирую отчёт...",
                data={
                    "period": period.value if period else None,
                    "action": "get_report",
                },
            )

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return CommandResult(
                success=False,
                message=f"Ошибка при формировании отчёта: {e!s}",
            )

    async def add_transaction(
        self,
        user_id: int,
        type_: str,
        amount: Decimal,
        category: str,
        period: str = "monthly",
        description: str | None = None,
        transaction_date: date | None = None,
    ) -> TransactionResponse:
        """Add transaction directly (bypass LLM).

        Args:
            user_id: User ID.
            type_: Transaction type.
            amount: Transaction amount.
            category: Transaction category.
            period: Accounting period.
            description: Optional description.
            transaction_date: Optional date.

        Returns:
            Created transaction response.
        """
        transaction = await self.repository.create_transaction(
            user_id=user_id,
            type_=type_,
            amount=amount,
            category=category,
            period=period,
            description=description,
            transaction_date=transaction_date,
        )

        return TransactionResponse(
            id=transaction.id,
            transaction_id=transaction.transaction_id,
            type=TransactionType(transaction.type),
            amount=transaction.amount,
            category=Category(transaction.category),
            period=Period(transaction.period),
            description=transaction.description,
            transaction_date=transaction.transaction_date,
            created_at=transaction.created_at,
        )

    async def get_report(
        self,
        user_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> FinancialReportResponse:
        """Get financial report.

        Args:
            user_id: User ID.
            start_date: Optional start date.
            end_date: Optional end date.

        Returns:
            Financial report response.
        """
        # Get totals by type
        totals = await self.repository.get_totals_by_type(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get totals by category (expenses only)
        category_totals = await self.repository.get_totals_by_category(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            type_="expense",
        )

        # Get recent transactions
        transactions, _ = await self.repository.get_transactions(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            limit=20,
        )

        # Calculate metrics
        total_income = totals.get("income", Decimal("0"))
        total_expenses = totals.get("expense", Decimal("0"))
        net_balance = total_income - total_expenses

        profit_margin = None
        if total_income > 0:
            profit_margin = float((net_balance / total_income) * 100)

        # Calculate category breakdown
        total_category = sum(category_totals.values()) or Decimal("1")
        by_category = [
            CategoryBreakdown(
                category=Category(cat),
                total=amount,
                percentage=float((amount / total_category) * 100),
            )
            for cat, amount in sorted(
                category_totals.items(),
                key=lambda x: x[1],
                reverse=True,
            )
        ]

        # Build period label
        if start_date and end_date:
            period_label = (
                f"{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}"
            )
        else:
            period_label = "Все время"

        return FinancialReportResponse(
            total_income=total_income,
            total_expenses=total_expenses,
            net_balance=net_balance,
            profit_margin=profit_margin,
            transactions=[
                TransactionResponse(
                    id=t.id,
                    transaction_id=t.transaction_id,
                    type=TransactionType(t.type),
                    amount=t.amount,
                    category=Category(t.category),
                    period=Period(t.period),
                    description=t.description,
                    transaction_date=t.transaction_date,
                    created_at=t.created_at,
                )
                for t in transactions
            ],
            by_category=by_category,
            period_label=period_label,
        )

    def _format_amount(self, amount: Decimal) -> str:
        """Format amount for display.

        Args:
            amount: Amount to format.

        Returns:
            Formatted string (e.g., "15 000 000").
        """
        return f"{amount:,.0f}".replace(",", " ")
