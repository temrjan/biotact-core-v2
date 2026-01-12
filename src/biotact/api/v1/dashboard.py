"""Dashboard endpoints for financial tracking."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query

from biotact.core.dependencies import CurrentUserDep, DashboardServiceDep
from biotact.schemas.dashboard import (
    AddFinancialRecordRequest,
    Category,
    DashboardKPI,
    FinancialReportResponse,
    Period,
    TransactionResponse,
    TransactionType,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.post("/transactions", response_model=TransactionResponse)
async def create_transaction(
    request: AddFinancialRecordRequest,
    current_user: CurrentUserDep,
    dashboard_service: DashboardServiceDep,
) -> TransactionResponse:
    """Create a new financial transaction.

    - **type**: expense or income
    - **amount**: Amount in currency units (must be > 0)
    - **category**: Transaction category
    - **period**: Accounting period (default: monthly)
    - **description**: Optional description
    - **transaction_date**: Optional date (default: today)
    """
    return await dashboard_service.add_transaction(
        user_id=current_user.id,
        type_=request.type.value,
        amount=request.amount,
        category=request.category.value,
        period=request.period.value,
        description=request.description,
        transaction_date=request.transaction_date,
    )


@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    current_user: CurrentUserDep,
    dashboard_service: DashboardServiceDep,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    category: Category | None = Query(default=None),
    type_: TransactionType | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[TransactionResponse]:
    """Get list of transactions with filters.

    - **start_date**: Filter by start date
    - **end_date**: Filter by end date
    - **category**: Filter by category
    - **type**: Filter by type (expense/income)
    - **limit**: Maximum number of transactions (1-200)
    - **offset**: Pagination offset
    """
    transactions, _ = await dashboard_service.repository.get_transactions(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        category=category.value if category else None,
        type_=type_.value if type_ else None,
        limit=limit,
        offset=offset,
    )

    return [
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
    ]


@router.get("/report", response_model=FinancialReportResponse)
async def get_report(
    current_user: CurrentUserDep,
    dashboard_service: DashboardServiceDep,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> FinancialReportResponse:
    """Get financial report for a period.

    - **start_date**: Report start date (optional)
    - **end_date**: Report end date (optional)

    Returns income, expenses, net balance, and breakdown by category.
    """
    return await dashboard_service.get_report(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/kpi", response_model=DashboardKPI)
async def get_kpi(
    current_user: CurrentUserDep,
    dashboard_service: DashboardServiceDep,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> DashboardKPI:
    """Get KPI metrics for dashboard cards.

    - **start_date**: Period start date (optional)
    - **end_date**: Period end date (optional)

    Returns revenue, expenses, profit, and profit margin.
    """
    totals = await dashboard_service.repository.get_totals_by_type(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )

    revenue = totals.get("income", Decimal("0"))
    expenses = totals.get("expense", Decimal("0"))
    profit = revenue - expenses

    profit_margin = 0.0
    if revenue > 0:
        profit_margin = float((profit / revenue) * 100)

    return DashboardKPI(
        revenue=revenue,
        expenses=expenses,
        profit=profit,
        profit_margin=profit_margin,
    )


@router.delete("/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    current_user: CurrentUserDep,
    dashboard_service: DashboardServiceDep,
) -> dict[str, bool]:
    """Delete a transaction.

    - **transaction_id**: Transaction ID to delete

    Returns success status.
    """
    deleted = await dashboard_service.repository.delete_transaction(
        transaction_id=transaction_id,
        user_id=current_user.id,
    )
    return {"deleted": deleted}
