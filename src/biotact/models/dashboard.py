"""Dashboard models for financial tracking."""

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from biotact.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from biotact.models.user import User


class FinancialTransaction(TimestampMixin, Base):
    """Financial transaction model."""

    __tablename__ = "financial_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # expense / income
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    period: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # monthly / quarterly / yearly
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    transaction_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<FinancialTransaction(id={self.id}, type='{self.type}', amount={self.amount})>"
