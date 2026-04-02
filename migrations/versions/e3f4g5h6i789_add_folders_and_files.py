"""Add folders and files tables for document storage module.

Revision ID: e3f4g5h6i789
Revises: d2e3f4g5h678
Create Date: 2026-04-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3f4g5h6i789"
down_revision: str | None = "d2e3f4g5h678"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create folders and files tables."""
    # Folders
    op.create_table(
        "folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "folder_id", sa.String(50), unique=True, index=True, nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("folders.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
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
        sa.UniqueConstraint(
            "parent_id",
            "name",
            name="uq_folders_parent_name",
            postgresql_nulls_not_distinct=True,
        ),
    )

    # Files
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "file_id", sa.String(50), unique=True, index=True, nullable=False
        ),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "folder_id",
            sa.Integer(),
            sa.ForeignKey("folders.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "uploaded_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "is_indexed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "share_token", sa.String(64), unique=True, nullable=True, index=True
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
    """Drop folders and files tables."""
    op.drop_table("files")
    op.drop_table("folders")
