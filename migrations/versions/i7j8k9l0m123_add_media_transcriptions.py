"""Add media_transcriptions table for STT history.

Revision ID: i7j8k9l0m123
Revises: h6i7j8k9l012
Create Date: 2026-04-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i7j8k9l0m123"
down_revision: str | None = "h6i7j8k9l012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create media_transcriptions table."""
    op.create_table(
        "media_transcriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "transcription_id",
            sa.String(50),
            unique=True,
            index=True,
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "uploaded_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
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
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop media_transcriptions table."""
    op.drop_table("media_transcriptions")
