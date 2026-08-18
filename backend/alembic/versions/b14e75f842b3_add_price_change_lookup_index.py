"""Add price_change lookup index

Revision ID: b14e75f842b3
Revises: 395f6e914130
Create Date: 2026-08-18 00:00:00.000000

Supports prices_daily()'s per-day forward-fill lookup: station_id,
fuel_description, self_service as equality filters (leading columns) then
entry_date as the trailing column for the ORDER BY entry_date DESC LIMIT 1
scan within that narrowed range.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b14e75f842b3'
down_revision: Union[str, Sequence[str], None] = 'e56169ee5fe2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # CONCURRENTLY avoids taking a lock that would block writers - price_change
    # is under continuous write load from the scraper.
    with op.get_context().autocommit_block():
        op.create_index(
            'idx_price_change_lookup',
            'price_change',
            ['station_id', 'fuel_description', 'self_service', 'entry_date'],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.get_context().autocommit_block():
        op.drop_index(
            'idx_price_change_lookup',
            table_name='price_change',
            postgresql_concurrently=True,
        )
