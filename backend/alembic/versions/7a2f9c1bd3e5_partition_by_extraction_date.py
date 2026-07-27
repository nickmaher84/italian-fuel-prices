"""Partition price_history and station_history by extraction_date (quarterly)

Revision ID: 7a2f9c1bd3e5
Revises: 9ffb438ca31b
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '7a2f9c1bd3e5'
down_revision: Union[str, Sequence[str], None] = '9ffb438ca31b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to partitioned tables. Partitions created for existing data range."""
    op.execute("CREATE SCHEMA data_partitions")
    conn = op.get_bind()

    def get_quarters_for_range(min_date, max_date):
        """Get list of (year, quarter) tuples needed to cover the date range."""
        if not min_date or not max_date:
            return []
        quarters = set()
        year, month = min_date.year, min_date.month
        max_year, max_month = max_date.year, max_date.month
        while (year, month) <= (max_year, max_month):
            quarter = (month - 1) // 3 + 1
            quarters.add((year, quarter))
            month += 3
            if month > 12:
                month = 1
                year += 1
        return sorted(quarters)

    # === PRICE_HISTORY ===
    op.rename_table('price_history', 'price_history_backup')
    op.create_index('idx_price_history_backup_file_id', 'price_history_backup', ['file_id'])
    op.drop_index('idx_price_history_file_id', 'price_history_backup')

    conn.execute(sa.text("""
        CREATE TABLE price_history (
            id UUID NOT NULL,
            station_id INTEGER NOT NULL,
            fuel_description VARCHAR(50) NOT NULL,
            self_service BOOLEAN NOT NULL,
            price NUMERIC(9,3) NOT NULL,
            entry_date TIMESTAMP NOT NULL,
            extraction_date DATE NOT NULL,
            file_id UUID NOT NULL,
            PRIMARY KEY (extraction_date, id),
            FOREIGN KEY (file_id) REFERENCES file(file_id)
        ) PARTITION BY RANGE (extraction_date)
    """))

    op.create_index('idx_price_history_file_id', 'price_history', ['file_id'])
    op.create_index('idx_price_history_extraction_date', 'price_history', ['extraction_date'])

    # Create partitions for date range in backup data
    result = conn.execute(sa.text("SELECT MIN(extraction_date), MAX(extraction_date) FROM price_history_backup"))
    min_date, max_date = result.fetchone()
    for year, quarter in get_quarters_for_range(min_date, max_date):
        start_month = (quarter - 1) * 3 + 1
        end_year = year + 1 if quarter == 4 else year
        end_month = 1 if quarter == 4 else start_month + 3
        start_date = f"{year:04d}-{start_month:02d}-01"
        end_date = f"{end_year:04d}-{end_month:02d}-01"
        partition_schema = "data_partitions"
        partition_name = f"price_history_{year}q{quarter}"
        conn.execute(sa.text(f"""
            CREATE TABLE {partition_schema}.{partition_name} PARTITION OF price_history
                FOR VALUES FROM ('{start_date}') TO ('{end_date}')
        """))

    conn.execute(sa.text("INSERT INTO price_history SELECT * FROM price_history_backup"))

    # === STATION_HISTORY ===
    op.rename_table('station_history', 'station_history_backup')
    op.create_index('idx_station_history_backup_file_id', 'station_history_backup', ['file_id'])
    op.drop_index('idx_station_history_file_id', 'station_history_backup')

    conn.execute(sa.text("""
        CREATE TABLE station_history (
            id UUID NOT NULL,
            station_id INTEGER NOT NULL,
            station_name VARCHAR(100),
            station_type VARCHAR(20) NOT NULL,
            operator_name VARCHAR(255),
            brand_name VARCHAR(50),
            address VARCHAR(255),
            comune VARCHAR(50),
            province_code VARCHAR(2),
            latitude FLOAT,
            longitude FLOAT,
            extraction_date DATE NOT NULL,
            file_id UUID NOT NULL,
            PRIMARY KEY (extraction_date, id),
            FOREIGN KEY (file_id) REFERENCES file(file_id)
        ) PARTITION BY RANGE (extraction_date)
    """))

    op.create_index('idx_station_history_file_id', 'station_history', ['file_id'])
    op.create_index('idx_station_history_extraction_date', 'station_history', ['extraction_date'])

    # Create partitions for date range in backup data
    result = conn.execute(sa.text("SELECT MIN(extraction_date), MAX(extraction_date) FROM station_history_backup"))
    min_date, max_date = result.fetchone()
    for year, quarter in get_quarters_for_range(min_date, max_date):
        start_month = (quarter - 1) * 3 + 1
        end_year = year + 1 if quarter == 4 else year
        end_month = 1 if quarter == 4 else start_month + 3
        start_date = f"{year:04d}-{start_month:02d}-01"
        end_date = f"{end_year:04d}-{end_month:02d}-01"
        partition_schema = "data_partitions"
        partition_name = f"station_history_{year}q{quarter}"
        conn.execute(sa.text(f"""
            CREATE TABLE {partition_schema}.{partition_name} PARTITION OF station_history
                FOR VALUES FROM ('{start_date}') TO ('{end_date}')
        """))

    conn.execute(sa.text("INSERT INTO station_history SELECT * FROM station_history_backup"))


def downgrade() -> None:
    """Downgrade schema (restore from backup tables or recreate schema). Idempotent—safe to retry."""
    op.drop_table('price_history')
    op.create_index('idx_price_history_file_id', 'price_history_backup', ['file_id'])
    op.drop_index('idx_price_history_backup_file_id', 'price_history_backup')
    op.rename_table('price_history_backup', 'price_history')

    op.drop_table('station_history')
    op.create_index('idx_station_history_file_id', 'station_history_backup', ['file_id'])
    op.drop_index('idx_station_history_backup_file_id', 'station_history_backup')
    op.rename_table('station_history_backup', 'station_history')

    op.execute("DROP SCHEMA data_partitions")
