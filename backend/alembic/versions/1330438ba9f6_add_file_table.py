"""Add file table

Revision ID: 1330438ba9f6
Revises: 
Create Date: 2026-06-29 23:10:28.931662

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1330438ba9f6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    file_type_enum = sa.Enum('PRICES', 'STATIONS', name='file_type')

    op.create_table(
        'file',
        sa.Column('file_id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('extension', sa.String(length=255), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('checksum', sa.String(length=255), nullable=False),
        sa.Column('modified', sa.DateTime(), nullable=True),
        sa.Column('loaded', sa.DateTime(), nullable=True),
        sa.Column('file_type', file_type_enum, nullable=True),
        sa.PrimaryKeyConstraint('file_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('file')
    sa.Enum(name='file_type').drop(op.get_bind(), checkfirst=True)
