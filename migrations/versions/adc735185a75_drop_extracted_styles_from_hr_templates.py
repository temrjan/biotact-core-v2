"""drop extracted_styles from hr_templates

Revision ID: adc735185a75
Revises: j8k9l0m1n234
Create Date: 2026-06-09 10:37:08.557312

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'adc735185a75'
down_revision: Union[str, Sequence[str], None] = 'j8k9l0m1n234'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop extracted_styles column from hr_templates."""
    op.drop_column('hr_templates', 'extracted_styles')


def downgrade() -> None:
    """Add extracted_styles column back to hr_templates."""
    op.add_column(
        'hr_templates',
        sa.Column('extracted_styles', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
