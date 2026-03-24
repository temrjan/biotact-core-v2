"""Dashboard schemas for financial tracking."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TransactionType(StrEnum):
    """Transaction type enum."""

    EXPENSE = "expense"
    INCOME = "income"


class Category(StrEnum):
    """Financial category enum."""

    HOSTING = "hosting"
    MARKETING = "marketing"
    SALARY = "salary"
    INVENTORY = "inventory"
    OFFICE = "office"
    LOGISTICS = "logistics"
    OTHER = "other"
    SALES = "sales"


class Period(StrEnum):
    """Accounting period enum."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


# Request Schemas


class AddFinancialRecordRequest(BaseModel):
    """Request to add a financial record."""

    type: TransactionType
    amount: Decimal = Field(gt=0, description="Amount in currency units")
    category: Category
    period: Period = Period.MONTHLY
    description: str | None = Field(default=None, max_length=500)
    transaction_date: date | None = None


class GetFinancialReportRequest(BaseModel):
    """Request to get financial report."""

    period: Period | None = None
    start_date: date | None = None
    end_date: date | None = None


class DashboardQueryRequest(BaseModel):
    """Request for natural language dashboard query."""

    message: str = Field(min_length=1, max_length=4000)


# Response Schemas


class TransactionResponse(BaseModel):
    """Response for a single transaction."""

    id: int
    transaction_id: str
    type: TransactionType
    amount: Decimal
    category: Category
    period: Period
    description: str | None
    transaction_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


class CategoryBreakdown(BaseModel):
    """Breakdown by category."""

    category: Category
    total: Decimal
    percentage: float


class FinancialReportResponse(BaseModel):
    """Response for financial report."""

    total_income: Decimal
    total_expenses: Decimal
    net_balance: Decimal
    profit_margin: float | None = None
    transactions: list[TransactionResponse]
    by_category: list[CategoryBreakdown]
    period_label: str


class DashboardKPI(BaseModel):
    """KPI data for dashboard cards."""

    revenue: Decimal
    expenses: Decimal
    profit: Decimal
    profit_margin: float


class DashboardQueryResponse(BaseModel):
    """Response for natural language dashboard query."""

    answer: str
    action_result: dict[str, Any] | None = None
