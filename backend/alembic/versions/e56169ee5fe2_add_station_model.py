"""Add station model

Revision ID: e56169ee5fe2
Revises: 6e8d80ca6e2f
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e56169ee5fe2'
down_revision: Union[str, Sequence[str], None] = '6e8d80ca6e2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'station',
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
        sa.Column('extraction_date', sa.Date(), nullable=False),
        sa.Column('file_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['file.file_id'], name='fk_station_file_id'),
        sa.PrimaryKeyConstraint('station_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('station')
