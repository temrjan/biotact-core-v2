"""HR Events models — calendar of employee occasions."""

from datetime import date
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column

from biotact.models.base import Base, TimestampMixin


class OccasionType(StrEnum):
    """Types of employee occasions tracked in the calendar."""

    BIRTHDAY = "birthday"
    WEDDING = "wedding"
    ANNIVERSARY = "anniversary"
    HOLIDAY = "holiday"
    OTHER = "other"


class HREvent(TimestampMixin, Base):
    """Calendar event for an employee occasion.

    Tracks birthdays, weddings, anniversaries, and holidays.
    Independent from gift requests — an event may exist without
    an associated gift request.
    """

    __tablename__ = "hr_events"
    __table_args__ = (
        Index("ix_hr_event_date", "date"),
        Index("ix_hr_event_department", "department"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    employee_name: Mapped[str] = mapped_column(String(300), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    # values_callable: persist enum *values* ("birthday"), not member
    # names ("BIRTHDAY") — the hr_occasion_type type created by migration
    # k9l0m1n2o345 holds lowercase values (see gifts/models.py).
    occasion_type: Mapped[OccasionType] = mapped_column(
        PGEnum(
            OccasionType,
            name="hr_occasion_type",
            create_type=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<HREvent(id={self.id}, "
            f"employee='{self.employee_name}', "
            f"type='{self.occasion_type.value}', "
            f"date='{self.date}')>"
        )
