"""Add indexes on file_id columns

Revision ID: 687a696385f4
Revises: 041d080ed120
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '687a696385f4'
down_revision: Union[str, Sequence[str], None] = '041d080ed120'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_price_history_file_id', 'price_history', ['file_id'])
    op.create_index('idx_station_history_file_id', 'station_history', ['file_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_station_history_file_id', 'station_history')
    op.drop_index('idx_price_history_file_id', 'price_history')
