"""Add HR gifts and events tables.

Creates:
- hr_events (calendar occasions)
- hr_gift_budget_plans (monthly budget planning)
- hr_gift_requests (gift registry with pipeline status)
- hr_gift_status_history (audit trail for status changes)

Revision ID: k9l0m1n2o345
Revises: j8k9l0m1n234
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "k9l0m1n2o345"
down_revision: str | None = "j8k9l0m1n234"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create HR gifts and events tables with indexes and enums."""
    # Create enum types
    hr_occasion_type = postgresql.ENUM(
        "birthday",
        "wedding",
        "anniversary",
        "holiday",
        "other",
        name="hr_occasion_type",
        create_type=True,
    )
    hr_occasion_type.create(op.get_bind(), checkfirst=True)

    hr_gift_status = postgresql.ENUM(
        "new",
        "approval",
        "purchase",
        "packaging",
        "ready",
        "done",
        "cancelled",
        name="hr_gift_status",
        create_type=True,
    )
    hr_gift_status.create(op.get_bind(), checkfirst=True)

    # hr_events
    op.create_table(
        "hr_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("employee_name", sa.String(length=300), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=False),
        sa.Column(
            "occasion_type",
            postgresql.ENUM(
                "birthday",
                "wedding",
                "anniversary",
                "holiday",
                "other",
                name="hr_occasion_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_hr_events_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hr_events")),
    )
    op.create_index(
        op.f("ix_hr_event_date"), "hr_events", ["date"], unique=False
    )
    op.create_index(
        op.f("ix_hr_event_department"), "hr_events", ["department"], unique=False
    )

    # hr_gift_budget_plans
    op.create_table(
        "hr_gift_budget_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("planned_amount", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_hr_gift_budget_plans_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_hr_gift_budget_plans")
        ),
        sa.UniqueConstraint(
            "month",
            "year",
            name=op.f("uq_hr_gift_budget_plans_month_year"),
        ),
    )

    # hr_gift_requests
    op.create_table(
        "hr_gift_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("initiator", sa.String(length=300), nullable=False),
        sa.Column("recipient", sa.String(length=300), nullable=False),
        sa.Column("occasion", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("gift_name", sa.String(length=300), nullable=True),
        sa.Column("budget", sa.Integer(), nullable=False),
        sa.Column("vendor", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "new",
                "approval",
                "purchase",
                "packaging",
                "ready",
                "done",
                "cancelled",
                name="hr_gift_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("presentation_date", sa.Date(), nullable=True),
        sa.Column("responsible_person_id", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_hr_gift_requests_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["hr_events.id"],
            name=op.f("fk_hr_gift_requests_event_id_hr_events"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_person_id"],
            ["users.id"],
            name=op.f("fk_hr_gift_requests_responsible_person_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hr_gift_requests")),
    )
    op.create_index(
        op.f("ix_gift_request_created_at"),
        "hr_gift_requests",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gift_request_presentation_date"),
        "hr_gift_requests",
        ["presentation_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gift_request_responsible"),
        "hr_gift_requests",
        ["responsible_person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gift_request_status"),
        "hr_gift_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gift_request_event_id"),
        "hr_gift_requests",
        ["event_id"],
        unique=False,
    )

    # hr_gift_status_history
    op.create_table(
        "hr_gift_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column(
            "from_status",
            postgresql.ENUM(
                "new",
                "approval",
                "purchase",
                "packaging",
                "ready",
                "done",
                "cancelled",
                name="hr_gift_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "to_status",
            postgresql.ENUM(
                "new",
                "approval",
                "purchase",
                "packaging",
                "ready",
                "done",
                "cancelled",
                name="hr_gift_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("changed_by", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_hr_gift_status_history_changed_by_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["hr_gift_requests.id"],
            name=op.f(
                "fk_hr_gift_status_history_request_id_hr_gift_requests"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_hr_gift_status_history")
        ),
    )
    op.create_index(
        op.f("ix_gift_status_history_created_at"),
        "hr_gift_status_history",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gift_status_history_request_id"),
        "hr_gift_status_history",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gift_status_history_changed_by"),
        "hr_gift_status_history",
        ["changed_by"],
        unique=False,
    )


def downgrade() -> None:
    """Drop HR gifts and events tables and enum types."""
    op.drop_index(
        op.f("ix_gift_status_history_request_id"),
        table_name="hr_gift_status_history",
    )
    op.drop_index(
        op.f("ix_gift_status_history_changed_by"),
        table_name="hr_gift_status_history",
    )
    op.drop_index(
        op.f("ix_gift_status_history_created_at"),
        table_name="hr_gift_status_history",
    )
    op.drop_table("hr_gift_status_history")

    op.drop_index(
        op.f("ix_gift_request_status"), table_name="hr_gift_requests"
    )
    op.drop_index(
        op.f("ix_gift_request_event_id"), table_name="hr_gift_requests"
    )
    op.drop_index(
        op.f("ix_gift_request_responsible"), table_name="hr_gift_requests"
    )
    op.drop_index(
        op.f("ix_gift_request_presentation_date"),
        table_name="hr_gift_requests",
    )
    op.drop_index(
        op.f("ix_gift_request_created_at"), table_name="hr_gift_requests"
    )
    op.drop_table("hr_gift_requests")

    op.drop_table("hr_gift_budget_plans")

    op.drop_index(
        op.f("ix_hr_event_department"), table_name="hr_events"
    )
    op.drop_index(op.f("ix_hr_event_date"), table_name="hr_events")
    op.drop_table("hr_events")

    # Drop enum types
    hr_gift_status = postgresql.ENUM(
        "new",
        "approval",
        "purchase",
        "packaging",
        "ready",
        "done",
        "cancelled",
        name="hr_gift_status",
        create_type=False,
    )
    hr_gift_status.drop(op.get_bind(), checkfirst=True)

    hr_occasion_type = postgresql.ENUM(
        "birthday",
        "wedding",
        "anniversary",
        "holiday",
        "other",
        name="hr_occasion_type",
        create_type=False,
    )
    hr_occasion_type.drop(op.get_bind(), checkfirst=True)
