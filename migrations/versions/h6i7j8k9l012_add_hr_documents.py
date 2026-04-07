"""Add hr_documents table for tracking generated documents.

Revision ID: h6i7j8k9l012
Revises: g5h6i7j8k901
Create Date: 2026-04-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h6i7j8k9l012"
down_revision: str | None = "g5h6i7j8k901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create hr_documents table."""
    op.create_table(
        "hr_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.String(32), nullable=False, unique=True, index=True),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("hr_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("template_name", sa.String(300), nullable=False),
        sa.Column("employee_name", sa.String(300), nullable=False, index=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Drop hr_documents table."""
    op.drop_table("hr_documents")
