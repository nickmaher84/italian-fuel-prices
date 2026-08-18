"""Add price_change table

Revision ID: 6e8d80ca6e2f
Revises: 395f6e914130
Create Date: 2026-08-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e8d80ca6e2f'
down_revision: Union[str, Sequence[str], None] = '395f6e914130'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'price_change',
        sa.Column('price_hash', sa.LargeBinary(length=16), nullable=False),
        sa.Column('station_id', sa.Integer(), nullable=False),
        sa.Column('fuel_description', sa.String(length=50), nullable=False),
        sa.Column('self_service', sa.Boolean(), nullable=False),
        sa.Column('price', sa.Numeric(9, 3), nullable=False),
        sa.Column('entry_date', sa.DateTime(), nullable=False),
        sa.Column('min_extraction_date', sa.Date(), nullable=False),
        sa.Column('max_extraction_date', sa.Date(), nullable=False),
        sa.Column('first_file_id', sa.UUID(), nullable=False),
        sa.Column('last_file_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['first_file_id'], ['file.file_id'], name='fk_price_change_first_file_id'),
        sa.ForeignKeyConstraint(['last_file_id'], ['file.file_id'], name='fk_price_change_last_file_id'),
        sa.PrimaryKeyConstraint('price_hash'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('price_change')
