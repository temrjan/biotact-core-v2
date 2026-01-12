"""Add conversation_insights table for extraction agent.

Revision ID: d2e3f4g5h678
Revises: 3531b10eaadb
Create Date: 2026-02-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d2e3f4g5h678"
down_revision: str | None = "3531b10eaadb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create conversation_insights table."""
    op.create_table(
        "conversation_insights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "products",
            postgresql.ARRAY(sa.String()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "symptoms",
            postgresql.ARRAY(sa.String()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "family_members",
            postgresql.JSONB(),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("client_age", sa.Integer(), nullable=True),
        sa.Column("intent", sa.String(30), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("semantic_summary", sa.Text(), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("TRUE"),
            nullable=False,
        ),
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
    )
    # Partial index: fast lookup for active conversation per user
    op.create_index(
        "idx_ci_telegram_active",
        "conversation_insights",
        ["telegram_id"],
        unique=False,
        postgresql_where=sa.text("is_active = TRUE"),
    )


def downgrade() -> None:
    """Drop conversation_insights table."""
    op.drop_index("idx_ci_telegram_active", table_name="conversation_insights")
    op.drop_table("conversation_insights")
