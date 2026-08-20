"""allowed department id in user to be null

Revision ID: f0ff9c78bee3
Revises: 8738968bd53f
Create Date: 2026-07-28 09:11:41.057470

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0ff9c78bee3'
down_revision: Union[str, Sequence[str], None] = '8738968bd53f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
