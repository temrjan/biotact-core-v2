"""Add financial_transactions table

Revision ID: b2c3d4e5f678
Revises: 444f1aed1cc7
Create Date: 2026-01-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f678"
down_revision: str | Sequence[str] | None = "444f1aed1cc7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create financial_transactions table."""
    op.create_table(
        "financial_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "transaction_id", sa.String(50), unique=True, index=True, nullable=False
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),  # expense / income
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("category", sa.String(50), index=True, nullable=False),
        sa.Column("period", sa.String(20), nullable=False),  # monthly/quarterly/yearly
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("transaction_date", sa.Date(), index=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop financial_transactions table."""
    op.drop_table("financial_transactions")
