import logging
import math
from datetime import datetime, date
from werkzeug.http import parse_date
from pathlib import Path

from app.core import db
from app.db.models import File, FileType, ParserError

logger = logging.getLogger(__name__)


def ensure_partition_exists(session, table_name: str, extraction_date: date):
    """Create partition for extraction_date quarter if it doesn't exist.

    Only uses raw SQL for DDL (partition creation), which SQLAlchemy ORM cannot express.
    """
    if not extraction_date:
        return

    year = extraction_date.year
    month = extraction_date.month
    quarter = (month - 1) // 3 + 1
    schema_name = "data_partitions"
    partition_name = f"{table_name}_{year}q{quarter}"

    # Calculate partition boundaries
    start_month = (quarter - 1) * 3 + 1
    if quarter == 4:
        end_year = year + 1
        end_month = 1
    else:
        end_year = year
        end_month = start_month + 3

    start_date = f"{year:04d}-{start_month:02d}-01"
    end_date = f"{end_year:04d}-{end_month:02d}-01"

    conn = session.connection()

    # Check if partition exists using raw SQL (unavoidable for DDL introspection)
    check_sql = db.text(f"""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = '{partition_name}'
            AND table_schema = '{schema_name}'
        )
    """)
    exists = conn.execute(check_sql).scalar()

    if not exists:
        logger.info(f"Creating partition {partition_name} for {year}Q{quarter}")
        create_sql = db.text(f"""
            CREATE TABLE {schema_name}.{partition_name} PARTITION OF {table_name}
                FOR VALUES FROM ('{start_date}') TO ('{end_date}')
        """)
        conn.execute(create_sql)


def get_extension(filename):
    path = Path(filename)
    return ''.join(path.suffixes)


def get_file_type(filename):
    for file_type in FileType:
        if file_type.value in filename:
            return file_type
    return None


def get_or_create_file(session, conn, url):
    response = conn.head(url)
    response.raise_for_status()
    headers = response.headers

    checksum = headers.get('ETag', '').strip('"')
    modified = parse_date(response.headers.get("Last-Modified"))
    size = response.headers.get("Content-Length")

    existing = session.scalar(
        db.select(File).filter_by(filename=response.url, checksum=checksum)
    )

    if existing:
        return existing

    file = File(
        filename=response.url,
        extension=get_extension(response.url),
        checksum=checksum,
        modified=modified,
        size=size,
        file_type=get_file_type(response.url)
    )

    session.add(file)
    session.commit()

    return file


def get_or_create_member(session, member):
    checksum = member.chksum
    modified = datetime.fromtimestamp(member.mtime)
    size = member.size

    existing = session.scalar(
        db.select(File).filter_by(filename=member.name, checksum=str(checksum))
    )

    if existing:
        return existing

    file = File(
        filename=member.name,
        extension=get_extension(member.name),
        checksum=checksum,
        modified=modified,
        size=size,
        file_type=get_file_type(member.name),
    )

    session.add(file)
    session.commit()

    return file


def ingest_df(session, file, model, df):
    ensure_partition_exists(session, model.__tablename__, file.file_date())

    session.query(model).filter(model.file_id == file.file_id).delete()

    try:
        rows = df.to_dict(orient='records')
        rows = [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()} for row in rows]
        session.bulk_insert_mappings(model, rows)

        file.loaded = datetime.now()
        session.add(file)
        session.commit()

        logger.info(f"Inserted {len(df)} rows into {model.__tablename__}")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to insert into {model.__tablename__}: {e}")
        # raise


def save_errors(session, file, error_records):
    session.query(ParserError).filter(ParserError.file_id == file.file_id).delete()

    try:
        for idx, line in error_records:
            record = ParserError(
                file_id=file.file_id,
                line_number=idx,
                line=line,
            )
            session.add(record)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to insert into {ParserError.__tablename__}: {e}")
        raise

    file.loaded = datetime.now()
    session.add(file)
    session.commit()

    logger.info(f"Inserted {len(error_records)} rows into {ParserError.__tablename__}")
