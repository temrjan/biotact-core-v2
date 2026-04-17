"""Add enrichment fields to media_transcriptions.

Adds: summary (Text), keywords (JSONB array), is_indexed, chunk_count.

Revision ID: j8k9l0m1n234
Revises: i7j8k9l0m123
Create Date: 2026-04-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "j8k9l0m1n234"
down_revision: str | None = "i7j8k9l0m123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add enrichment columns."""
    op.add_column(
        "media_transcriptions",
        sa.Column(
            "summary",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "media_transcriptions",
        sa.Column(
            "keywords",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "media_transcriptions",
        sa.Column(
            "is_indexed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "media_transcriptions",
        sa.Column(
            "chunk_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    """Drop enrichment columns."""
    op.drop_column("media_transcriptions", "chunk_count")
    op.drop_column("media_transcriptions", "is_indexed")
    op.drop_column("media_transcriptions", "keywords")
    op.drop_column("media_transcriptions", "summary")
