"""Add prices_daily function

Revision ID: 081dd062ae06
Revises: b14e75f842b3
Create Date: 2026-08-18 00:00:01.000000

Ported from feature/transform-history's prices_daily() (over price_state)
to price_change. price_change tracks min/max_extraction_date the same way
price_state did, but the forward-fill boundary is entry_date - the true
submission date - not extraction_date, which only reflects which daily
snapshot file a row happened to be scraped in. See the price_state version
of this migration for the full reasoning/measurements behind that choice.

Unlike stations, prices change too often for a materialized daily table to
be worthwhile, so this is a set-returning function that forward-fills
price_change onto a calendar day per call, bounded by the caller's
start_date/end_date (and optional station_ids), so cost scales with the
requested range rather than full history.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '081dd062ae06'
down_revision: Union[str, Sequence[str], None] = 'b14e75f842b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE FUNCTION prices_daily(
            start_date date,
            end_date date,
            station_ids integer[] DEFAULT NULL
        )
        RETURNS TABLE (
            price_date date,
            station_id integer,
            fuel_description varchar(50),
            self_service boolean,
            price numeric(9,3),
            entry_date timestamp,
            price_hash varchar(32)
        )
        LANGUAGE sql STABLE AS $$
            SELECT
                d.price_date::date,
                k.station_id,
                k.fuel_description,
                k.self_service,
                pc.price,
                pc.entry_date,
                pc.price_hash
            FROM generate_series(start_date::timestamp, end_date::timestamp, interval '1 day') AS d(price_date)
            CROSS JOIN (
                SELECT DISTINCT station_id, fuel_description, self_service
                FROM price_change
                WHERE station_ids IS NULL OR station_id = ANY(station_ids)
            ) k
            JOIN LATERAL (
                SELECT price, entry_date, price_hash
                FROM price_change pc
                WHERE pc.station_id = k.station_id
                  AND pc.fuel_description = k.fuel_description
                  AND pc.self_service = k.self_service
                  AND pc.entry_date::date <= d.price_date::date
                ORDER BY pc.entry_date DESC
                LIMIT 1
            ) pc ON true;
        $$;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP FUNCTION IF EXISTS prices_daily(date, date, integer[])")
