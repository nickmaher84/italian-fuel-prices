import logging
import shutil
from datetime import date

import duckdb
import psutil

from app.config import Config
from app.quarters import quarter_chunks, DEFAULT_START_QUARTER

logger = logging.getLogger(__name__)

# Fraction of physical RAM DuckDB may use for a mirror sync when
# MIRROR_MEMORY_LIMIT is not set. Kept well under 1.0 so DuckDB spills to its
# temp files under pressure instead of letting the OS swap the whole process -
# on a small box the ~80% default leaves no headroom and thrashes.
MEMORY_LIMIT_FRACTION = 0.6


def duckdb_memory_limit() -> str:
    if Config.MIRROR_MEMORY_LIMIT:
        return Config.MIRROR_MEMORY_LIMIT

    gib = psutil.virtual_memory().total / 1024 ** 3
    return f"{max(1.0, gib * MEMORY_LIMIT_FRACTION):.1f}GB"


class Mirror:
    PATH = Config.MIRROR_PATH

    PRICE_CHANGE_COLUMNS = [
        "price_hash",
        "station_id",
        "fuel_description",
        "self_service",
        "price",
        "entry_date",
        "min_extraction_date",
        "max_extraction_date",
    ]

    PRICE_CHANGE_DDL = """
        price_hash BLOB,
        station_id INTEGER,
        fuel_description VARCHAR,
        self_service BOOLEAN,
        price DECIMAL(9,3),
        entry_date TIMESTAMP,
        min_extraction_date DATE,
        max_extraction_date DATE
    """

    STATION_COLUMNS = [
        "station_id",
        "station_name",
        "station_type",
        "operator_name",
        "brand_name",
        "comune",
        "province_code",
        "latitude",
        "longitude",
        "extraction_date",
    ]

    def connect(self, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        if not read_only:
            self.PATH.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.PATH), read_only=read_only)

    def writer(self) -> duckdb.DuckDBPyConnection:
        """A read-write connection tuned for bulk sync: a memory cap that leaves
        the OS headroom (so DuckDB spills rather than swaps) and insertion-order
        preservation off (the mirror is always queried with an explicit ORDER
        BY, so storage order is irrelevant)."""
        con = self.connect()
        con.execute("SET preserve_insertion_order = false")
        con.execute(f"SET memory_limit = '{duckdb_memory_limit()}'")
        return con

    def query(self, sql: str, params: list | None = None) -> list:
        con = self.connect(read_only=True)
        try:
            return con.execute(sql, params or []).fetchall()
        finally:
            con.close()

    def attach_postgres(self, con: duckdb.DuckDBPyConnection) -> None:
        """ATTACH is per-connection state, not persisted into the .duckdb file
        - every fresh connection needs this before it can read pg.* tables,
        and closing the connection (see callers below) already releases it
        cleanly, so there's no matching detach_postgres()."""
        con.execute("INSTALL postgres")
        con.execute("LOAD postgres")
        con.execute(f"ATTACH '{Config.PG_ATTACH_URI}' AS pg (TYPE postgres, READ_ONLY)")

    def _sync_price_chunk(self, chunk_start: date, chunk_end: date) -> int:
        """One chunk of an *incremental* price_change sync, on its own short-lived
        connection so DuckDB releases memory and checkpoints the WAL between
        chunks.

        Replaces the whole date slice wholesale: delete every mirror row whose
        [min_extraction_date, max_extraction_date] span overlaps
        [chunk_start, chunk_end], then re-insert that same overlapping slice from
        Postgres. The mirror has no price_hash index (a unique BLOB index over
        ~128M rows does not fit in RAM on this box), so matching by date range -
        which DuckDB can prune with zone maps - rather than by hash is both
        cheaper and naturally idempotent. The overlap predicate is used because
        loading a quarter can widen the max of a row whose min sits earlier.
        """
        columns = ", ".join(self.PRICE_CHANGE_COLUMNS)

        con = self.writer()
        try:
            self.attach_postgres(con)
            con.execute("BEGIN TRANSACTION")
            con.execute(
                "DELETE FROM price_change WHERE min_extraction_date <= ? AND max_extraction_date >= ?",
                [chunk_end, chunk_start],
            )
            count = con.execute(
                f"""
                INSERT INTO price_change
                SELECT {columns} FROM pg.price_change
                WHERE min_extraction_date <= ? AND max_extraction_date >= ?
                """,
                [chunk_end, chunk_start],
            ).fetchone()[0]
            con.execute("COMMIT")
            return count
        finally:
            con.close()

    def sync_price_range(self, start_date: date, end_date: date) -> int:
        """Incremental sync of the quarters overlapping [start_date, end_date] -
        used after a scrape has changed a bounded slice of price_change. For a
        from-scratch load use rebuild() / refresh(), which is far cheaper."""
        self.ensure_tables()

        logger.info("Refreshing price changes...")

        total = 0
        for chunk_start, chunk_end in quarter_chunks(start_date, end_date):
            count = self._sync_price_chunk(chunk_start, chunk_end)
            total += count
            logger.info(f"price_change: {chunk_start} to {chunk_end} synced, {count} rows")

        return total

    def _rebuild_price_change(self) -> int:
        """Load price_change from scratch, bucketed by min_extraction_date so
        every Postgres row lands in exactly one chunk. Much cheaper than the
        overlap query in sync_price_range - each chunk loads only that quarter's
        new rows, not every still-open historical span, and there is no delete
        or re-churn.

        The table has no price_hash index: a unique BLOB index over ~128M rows
        does not fit in RAM on this box (DuckDB does not spill index builds),
        and nothing needs it - prices_daily_mirror filters on the extraction
        dates, which DuckDB prunes with zone maps, and the incremental sync
        matches by date range too. Correct only from an empty table, which
        refresh() guarantees."""
        columns = ", ".join(self.PRICE_CHANGE_COLUMNS)

        con = self.writer()
        try:
            con.execute("DROP TABLE IF EXISTS price_change")
            con.execute(f"CREATE TABLE price_change ({self.PRICE_CHANGE_DDL})")
        finally:
            con.close()
        # Recreate the macro now so prices_daily() degrades to "no rows" rather
        # than erroring if the rebuild dies partway through.
        self._ensure_prices_daily_macro()

        total = 0
        start = DEFAULT_START_QUARTER.start_time.date()
        for chunk_start, chunk_end in quarter_chunks(start, date.today()):
            logger.info(f"price_change rebuild: loading {chunk_start} to {chunk_end}...")
            con = self.writer()
            try:
                self.attach_postgres(con)
                count = con.execute(
                    f"""
                    INSERT INTO price_change
                    SELECT {columns} FROM pg.price_change
                    WHERE min_extraction_date >= ? AND min_extraction_date <= ?
                    """,
                    [chunk_start, chunk_end],
                ).fetchone()[0]
            except Exception:
                logger.error(f"price_change rebuild FAILED loading {chunk_start} to {chunk_end}", exc_info=True)
                raise
            finally:
                con.close()
            total += count
            logger.info(f"price_change rebuild: {chunk_start} to {chunk_end} done, {count} rows ({total} total)")

        logger.info(f"price_change rebuild: complete, {total} rows")
        return total

    def sync_stations(self):
        con = self.writer()

        try:
            logger.info("Refreshing stations...")
            self.attach_postgres(con)

            columns = ", ".join(self.STATION_COLUMNS)
            con.execute(
                f"""
                CREATE OR REPLACE TABLE station AS 
                SELECT {columns} FROM pg.station
                """
            )
            total = con.execute("SELECT count(*) FROM station").fetchone()[0]
            logger.info(f"station: {total} rows")
        finally:
            con.close()

        return total

    def ensure_tables(self):
        con = self.connect()
        try:
            con.execute(
                f"CREATE TABLE IF NOT EXISTS price_change ({self.PRICE_CHANGE_DDL})"
            )
        finally:
            con.close()
        self._ensure_prices_daily_macro()

    def _ensure_prices_daily_macro(self):
        con = self.connect()
        try:
            con.execute(
                """
                CREATE OR REPLACE MACRO prices_daily_mirror(start_date, end_date) AS TABLE
                SELECT
                    d.price_date::date AS price_date,
                    pc.station_id,
                    pc.fuel_description,
                    pc.self_service,
                    pc.price,
                    pc.entry_date,
                    pc.price_hash
                FROM price_change pc,
                     generate_series(start_date::date, end_date::date, INTERVAL 1 day) AS d(price_date)
                WHERE pc.min_extraction_date <= d.price_date
                  AND pc.max_extraction_date >= d.price_date
                """
            )
        finally:
            con.close()

    def refresh(self) -> None:
        """Rebuild every mirror table from Postgres from scratch. sync_stations
        already replaces its table wholesale; _rebuild_price_change drops and
        reloads price_change."""
        self.sync_stations()
        count = self._rebuild_price_change()

        logger.info(f"Mirror refresh finished ({count} price rows) -> {self.PATH}")

    def rebuild(self) -> None:
        """Full clean rebuild: discard the mirror database file (and any WAL /
        spill left behind by a crash) and re-sync every table from Postgres.
        Use this when the mirror is corrupt or its schema has changed - a plain
        refresh() reuses the existing file and would carry the damage forward.
        """
        for path in (self.PATH, self.PATH.with_name(self.PATH.name + ".wal")):
            path.unlink(missing_ok=True)

        tmp = self.PATH.with_name(self.PATH.name + ".tmp")
        if tmp.is_dir():
            shutil.rmtree(tmp)

        logger.info(f"Mirror files cleared, rebuilding -> {self.PATH}")
        self.refresh()

    def prices_daily(self, start_date: date, end_date: date, station_ids: list[int] | None = None) -> list:
        sql = "SELECT * FROM prices_daily_mirror(?, ?)"
        params = [start_date, end_date]

        if station_ids:
            placeholders = ", ".join("?" for _ in station_ids)
            sql += f" WHERE station_id IN ({placeholders})"
            params += station_ids

        sql += " ORDER BY station_id, fuel_description, self_service, price_date"

        return self.query(sql, params)
