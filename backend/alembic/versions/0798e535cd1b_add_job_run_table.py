"""Add job_run table

Revision ID: 0798e535cd1b
Revises: 081dd062ae06
Create Date: 2026-08-18 17:53:33.416866

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0798e535cd1b'
down_revision: Union[str, Sequence[str], None] = '081dd062ae06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'job_run',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.String(155), nullable=False),
        sa.Column('task_name', sa.String(255), nullable=False),
        sa.Column('args', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('started', sa.DateTime(), nullable=True),
        sa.Column('finished', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('job_run')
