"""merge hr versioning and gifts heads

Revision ID: ab2268e5a041
Revises: 39cc2e6de306, k9l0m1n2o345
Create Date: 2026-06-09 16:11:07.545847

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab2268e5a041'
down_revision: Union[str, Sequence[str], None] = ('39cc2e6de306', 'k9l0m1n2o345')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
