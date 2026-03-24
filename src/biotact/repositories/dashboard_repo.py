"""Dashboard repository for financial transactions."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.models.dashboard import FinancialTransaction


def generate_transaction_id() -> str:
    """Generate unique transaction ID."""
    return f"txn_{uuid.uuid4().hex[:12]}"


class DashboardRepository:
    """Repository for Dashboard financial operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository.

        Args:
            session: Async database session.
        """
        self.session = session

    async def create_transaction(
        self,
        user_id: int,
        type_: str,
        amount: Decimal,
        category: str,
        period: str,
        description: str | None = None,
        transaction_date: date | None = None,
    ) -> FinancialTransaction:
        """Create a new financial transaction.

        Args:
            user_id: User ID.
            type_: Transaction type (expense/income).
            amount: Transaction amount.
            category: Transaction category.
            period: Accounting period.
            description: Optional description.
            transaction_date: Optional transaction date (defaults to today).

        Returns:
            Created transaction.
        """
        transaction = FinancialTransaction(
            transaction_id=generate_transaction_id(),
            user_id=user_id,
            type=type_,
            amount=amount,
            category=category,
            period=period,
            description=description,
            transaction_date=transaction_date or date.today(),
        )
        self.session.add(transaction)
        await self.session.flush()
        await self.session.refresh(transaction)
        return transaction

    async def get_transaction_by_id(
        self,
        transaction_id: str,
    ) -> FinancialTransaction | None:
        """Get transaction by ID.

        Args:
            transaction_id: Transaction ID string.

        Returns:
            Transaction or None if not found.
        """
        result = await self.session.execute(
            select(FinancialTransaction).where(
                FinancialTransaction.transaction_id == transaction_id
            )
        )
        return result.scalar_one_or_none()

    async def get_transactions(
        self,
        user_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
        category: str | None = None,
        type_: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[FinancialTransaction], int]:
        """Get transactions with filters and pagination.

        Args:
            user_id: User ID.
            start_date: Optional start date filter.
            end_date: Optional end date filter.
            category: Optional category filter.
            type_: Optional type filter.
            limit: Max results.
            offset: Pagination offset.

        Returns:
            Tuple of (transactions list, total count).
        """
        # Build base query
        query = select(FinancialTransaction).where(
            FinancialTransaction.user_id == user_id
        )
        count_query = select(func.count(FinancialTransaction.id)).where(
            FinancialTransaction.user_id == user_id
        )

        # Apply filters
        if start_date:
            query = query.where(FinancialTransaction.transaction_date >= start_date)
            count_query = count_query.where(
                FinancialTransaction.transaction_date >= start_date
            )
        if end_date:
            query = query.where(FinancialTransaction.transaction_date <= end_date)
            count_query = count_query.where(
                FinancialTransaction.transaction_date <= end_date
            )
        if category:
            query = query.where(FinancialTransaction.category == category)
            count_query = count_query.where(FinancialTransaction.category == category)
        if type_:
            query = query.where(FinancialTransaction.type == type_)
            count_query = count_query.where(FinancialTransaction.type == type_)

        # Get total count
        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        # Get transactions with pagination
        query = (
            query.order_by(FinancialTransaction.transaction_date.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        transactions = list(result.scalars().all())

        return transactions, total

    async def get_totals_by_type(
        self,
        user_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Decimal]:
        """Get total income and expenses.

        Args:
            user_id: User ID.
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            Dict with 'income' and 'expense' totals.
        """
        query = select(
            FinancialTransaction.type,
            func.sum(FinancialTransaction.amount).label("total"),
        ).where(FinancialTransaction.user_id == user_id)

        if start_date:
            query = query.where(FinancialTransaction.transaction_date >= start_date)
        if end_date:
            query = query.where(FinancialTransaction.transaction_date <= end_date)

        query = query.group_by(FinancialTransaction.type)
        result = await self.session.execute(query)

        totals: dict[str, Decimal] = {"income": Decimal("0"), "expense": Decimal("0")}
        for row in result.all():
            if row.type in totals:
                totals[row.type] = Decimal(str(row.total or 0))

        return totals

    async def get_totals_by_category(
        self,
        user_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
        type_: str | None = None,
    ) -> dict[str, Decimal]:
        """Get totals grouped by category.

        Args:
            user_id: User ID.
            start_date: Optional start date filter.
            end_date: Optional end date filter.
            type_: Optional type filter (expense/income).

        Returns:
            Dict mapping category to total amount.
        """
        query = select(
            FinancialTransaction.category,
            func.sum(FinancialTransaction.amount).label("total"),
        ).where(FinancialTransaction.user_id == user_id)

        if start_date:
            query = query.where(FinancialTransaction.transaction_date >= start_date)
        if end_date:
            query = query.where(FinancialTransaction.transaction_date <= end_date)
        if type_:
            query = query.where(FinancialTransaction.type == type_)

        query = query.group_by(FinancialTransaction.category)
        result = await self.session.execute(query)

        return {row.category: Decimal(str(row.total or 0)) for row in result.all()}

    async def delete_transaction(
        self,
        transaction_id: str,
        user_id: int,
    ) -> bool:
        """Delete a transaction.

        Args:
            transaction_id: Transaction ID.
            user_id: User ID (for ownership check).

        Returns:
            True if deleted, False if not found.
        """
        transaction = await self.get_transaction_by_id(transaction_id)
        if transaction and transaction.user_id == user_id:
            await self.session.delete(transaction)
            await self.session.flush()
            return True
        return False
