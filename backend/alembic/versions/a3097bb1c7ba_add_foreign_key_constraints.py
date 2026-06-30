"""Add foreign key constraints

Revision ID: a3097bb1c7ba
Revises: 041d080ed120
Create Date: 2026-06-30 08:13:15.200630

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3097bb1c7ba'
down_revision: Union[str, Sequence[str], None] = '041d080ed120'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('price_history', schema=None) as batch_op:
        batch_op.alter_column('entry_date',
                   existing_type=sa.DATE(),
                   type_=sa.DateTime(),
                   nullable=True)
        batch_op.alter_column('file_id',
                   existing_type=sa.NUMERIC(),
                   type_=sa.UUID(as_uuid=False),
                   existing_nullable=False)
        batch_op.create_foreign_key('fk_price_history_file_id', 'file', ['file_id'], ['file_id'], ondelete='CASCADE')

    with op.batch_alter_table('station_history', schema=None) as batch_op:
        batch_op.alter_column('file_id',
                   existing_type=sa.NUMERIC(),
                   type_=sa.UUID(as_uuid=False),
                   existing_nullable=False)
        batch_op.create_foreign_key('fk_station_history_file_id', 'file', ['file_id'], ['file_id'], ondelete='CASCADE')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('station_history', schema=None) as batch_op:
        batch_op.drop_constraint('fk_station_history_file_id', type_='foreignkey')
        batch_op.alter_column('file_id',
                   existing_type=sa.UUID(as_uuid=False),
                   type_=sa.NUMERIC(),
                   existing_nullable=False)

    with op.batch_alter_table('price_history', schema=None) as batch_op:
        batch_op.drop_constraint('fk_price_history_file_id', type_='foreignkey')
        batch_op.alter_column('file_id',
                   existing_type=sa.UUID(as_uuid=False),
                   type_=sa.NUMERIC(),
                   existing_nullable=False)
        batch_op.alter_column('entry_date',
                   existing_type=sa.DateTime(),
                   type_=sa.DATE(),
                   nullable=False)
