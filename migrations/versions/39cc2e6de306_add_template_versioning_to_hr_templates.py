"""Add template versioning columns to hr_templates.

Adds version, is_active, and superseded_by_id to hr_templates with a
partial unique index ensuring only one active template per category.

On PostgreSQL 16, adding NOT NULL columns with a server_default is a
metadata-only operation (no table rewrite) because the default value is
stored in pg_attribute.attmissingval and backfilled lazily.

Revision ID: 39cc2e6de306
Revises: adc735185a75
Create Date: 2026-06-09 11:17:51.411181

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "39cc2e6de306"
down_revision: str | None = "adc735185a75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add versioning columns, unique constraint, and partial unique index."""
    # Add version column with default 1 for existing rows.
    op.add_column(
        "hr_templates",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    # Add is_active flag with default true for existing rows.
    op.add_column(
        "hr_templates",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # Add self-referencing FK for superseded-by chain.
    op.add_column(
        "hr_templates",
        sa.Column(
            "superseded_by_id",
            sa.Integer(),
            sa.ForeignKey("hr_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Ensure (category, version) pairs are unique.
    op.create_unique_constraint(
        "uq_hr_template_category_version",
        "hr_templates",
        ["category", "version"],
    )

    # Allow only one active template per category.
    op.create_index(
        "ix_hr_template_active_per_category",
        "hr_templates",
        ["category"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade() -> None:
    """Remove versioning columns, unique constraint, and partial unique index."""
    op.drop_index(
        "ix_hr_template_active_per_category",
        table_name="hr_templates",
        postgresql_where=sa.text("is_active IS TRUE"),
    )
    op.drop_constraint(
        "uq_hr_template_category_version",
        "hr_templates",
        type_="unique",
    )
    op.drop_column("hr_templates", "superseded_by_id")
    op.drop_column("hr_templates", "is_active")
    op.drop_column("hr_templates", "version")
