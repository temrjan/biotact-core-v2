"""HR Gifts models — gift requests, budget plans, and status audit."""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column

from biotact.models.base import Base, TimestampMixin


class GiftStatus(StrEnum):
    """Pipeline statuses for a gift request."""

    NEW = "new"
    APPROVAL = "approval"
    PURCHASE = "purchase"
    PACKAGING = "packaging"
    READY = "ready"
    DONE = "done"
    CANCELLED = "cancelled"


class GiftRequest(TimestampMixin, Base):
    """Gift request — tracks gifts, congratulations, and corporate events.

    Links optionally to HREvent for calendar integration.
    Status changes are audited in GiftStatusHistory.
    """

    __tablename__ = "hr_gift_requests"
    __table_args__ = (
        Index("ix_gift_request_status", "status"),
        Index("ix_gift_request_presentation_date", "presentation_date"),
        Index("ix_gift_request_created_at", "created_at"),
        Index("ix_gift_request_responsible", "responsible_person_id"),
        Index("ix_gift_request_event_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("hr_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    initiator: Mapped[str] = mapped_column(String(300), nullable=False)
    recipient: Mapped[str] = mapped_column(String(300), nullable=False)
    occasion: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    gift_name: Mapped[str | None] = mapped_column(String(300))
    budget: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vendor: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[GiftStatus] = mapped_column(
        PGEnum(
            GiftStatus,
            name="hr_gift_status",
            create_type=True,
        ),
        nullable=False,
        default=GiftStatus.NEW,
    )
    presentation_date: Mapped[date | None] = mapped_column(Date)
    responsible_person_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<GiftRequest(id={self.id}, "
            f"recipient='{self.recipient}', "
            f"status='{self.status.value}')>"
        )


class GiftBudgetPlan(TimestampMixin, Base):
    """Planned budget for gifts per month.

    Set by HR at the start of the month. Actual spend is computed
    from GiftRequest.budget via SQL aggregation.
    """

    __tablename__ = "hr_gift_budget_plans"
    __table_args__ = (
        UniqueConstraint(
            "month",
            "year",
            name="uq_hr_gift_budget_plans_month_year",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<GiftBudgetPlan(month={self.month}, "
            f"year={self.year}, "
            f"planned={self.planned_amount})>"
        )


class GiftStatusHistory(Base):
    """Audit trail for gift request status transitions.

    Append-only log — records are never updated or deleted.
    Uses created_at from TimestampMixin, but intentionally omits
    updated_at since audit records are immutable.
    """

    __tablename__ = "hr_gift_status_history"
    __table_args__ = (
        Index("ix_gift_status_history_request_id", "request_id"),
        Index("ix_gift_status_history_changed_by", "changed_by"),
        Index("ix_gift_status_history_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("hr_gift_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    from_status: Mapped[GiftStatus] = mapped_column(
        PGEnum(
            GiftStatus,
            name="hr_gift_status",
            create_type=True,
        ),
        nullable=False,
    )
    to_status: Mapped[GiftStatus] = mapped_column(
        PGEnum(
            GiftStatus,
            name="hr_gift_status",
            create_type=True,
        ),
        nullable=False,
    )
    changed_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<GiftStatusHistory(request={self.request_id}, "
            f"{self.from_status.value} → {self.to_status.value}, "
            f"by={self.changed_by})>"
        )
