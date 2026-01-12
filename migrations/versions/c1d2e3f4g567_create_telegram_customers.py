"""Create telegram_customers table for CRM.

Revision ID: c1d2e3f4g567
Revises: b2c3d4e5f678
Create Date: 2026-01-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4g567"
down_revision: str | None = "b2c3d4e5f678"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create telegram_customers table."""
    op.create_table(
        "telegram_customers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("language_code", sa.String(5), server_default="ru", nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column(
            "problems",
            postgresql.ARRAY(sa.String()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "family",
            postgresql.JSONB(),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "purchased_products",
            postgresql.ARRAY(sa.String()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("ai_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    # Create index for fast lookup by telegram_id
    op.create_index(
        "idx_telegram_customers_telegram_id",
        "telegram_customers",
        ["telegram_id"],
    )


def downgrade() -> None:
    """Drop telegram_customers table."""
    op.drop_index("idx_telegram_customers_telegram_id", table_name="telegram_customers")
    op.drop_table("telegram_customers")
