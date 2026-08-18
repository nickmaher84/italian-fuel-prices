"""Add station_change table

Revision ID: 395f6e914130
Revises: 1330438ba9f6
Create Date: 2026-07-28 22:19:54.893347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '395f6e914130'
down_revision: Union[str, Sequence[str], None] = '1330438ba9f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'station_change',
        sa.Column('station_hash', sa.LargeBinary(length=16), nullable=False),
        sa.Column('station_id', sa.Integer(), nullable=False),
        sa.Column('station_name', sa.String(length=100), nullable=True),
        sa.Column('station_type', sa.String(length=20), nullable=False),
        sa.Column('operator_name', sa.String(length=255), nullable=True),
        sa.Column('brand_name', sa.String(length=50), nullable=True),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('comune', sa.String(length=50), nullable=True),
        sa.Column('province_code', sa.String(length=2), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('min_extraction_date', sa.Date(), nullable=False),
        sa.Column('max_extraction_date', sa.Date(), nullable=False),
        sa.Column('first_file_id', sa.UUID(), nullable=False),
        sa.Column('last_file_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['first_file_id'], ['file.file_id'], name='fk_price_change_first_file_id'),
        sa.ForeignKeyConstraint(['last_file_id'], ['file.file_id'], name='fk_price_change_last_file_id'),
        sa.PrimaryKeyConstraint('station_hash')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('station_change')
