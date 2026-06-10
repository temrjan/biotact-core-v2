"""add_hr_gift_kpi_table

Revision ID: 0e5726777f0f
Revises: ab2268e5a041
Create Date: 2026-06-10 15:59:12.266282

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0e5726777f0f'
down_revision: str | Sequence[str] | None = 'ab2268e5a041'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create hr_gift_kpi table with unique month/year constraint."""
    op.create_table(
        "hr_gift_kpi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("employee_congrats_planned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("employee_congrats_actual", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partner_congrats_planned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partner_congrats_actual", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_compliance_planned", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("budget_compliance_actual", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("satisfaction_planned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("satisfaction_actual", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timely_closure_planned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timely_closure_actual", sa.Integer(), nullable=False, server_default="0"),
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
            name=op.f("fk_hr_gift_kpi_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hr_gift_kpi")),
        sa.UniqueConstraint(
            "month",
            "year",
            name=op.f("uq_hr_gift_kpi_month_year"),
        ),
    )


def downgrade() -> None:
    """Drop hr_gift_kpi table."""
    op.drop_table("hr_gift_kpi")
