"""Add template_fields column to hr_templates.

Revision ID: g5h6i7j8k901
Revises: f4g5h6i7j890
Create Date: 2026-04-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "g5h6i7j8k901"
down_revision: str | None = "f4g5h6i7j890"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add template_fields JSONB column."""
    op.add_column(
        "hr_templates",
        sa.Column("template_fields", postgresql.JSONB(), nullable=True, server_default="[]"),
    )


def downgrade() -> None:
    """Remove template_fields column."""
    op.drop_column("hr_templates", "template_fields")
