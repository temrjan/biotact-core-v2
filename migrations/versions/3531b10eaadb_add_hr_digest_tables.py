"""Add HR Digest tables.

Revision ID: 3531b10eaadb
Revises: c1d2e3f4g567
Create Date: 2026-02-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3531b10eaadb"
down_revision: str | None = "c1d2e3f4g567"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create HR Digest tables."""
    # Create hr_digests table
    op.create_table(
        "hr_digests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(), nullable=False),
        sa.Column("news_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("generated_by", sa.String(50), server_default="auto", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date"),
    )

    # Create indexes for hr_digests
    op.create_index("idx_hr_digests_date", "hr_digests", ["date"], unique=True)

    # Create hr_news_items table
    op.create_table(
        "hr_news_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "digest_id",
            sa.Integer(),
            sa.ForeignKey("hr_digests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create index for source lookup
    op.create_index("idx_hr_news_items_source", "hr_news_items", ["source"])


def downgrade() -> None:
    """Drop HR Digest tables."""
    op.drop_index("idx_hr_news_items_source", table_name="hr_news_items")
    op.drop_table("hr_news_items")
    op.drop_index("idx_hr_digests_date", table_name="hr_digests")
    op.drop_table("hr_digests")
