import logging
import math
from datetime import datetime
from werkzeug.http import parse_date
from pathlib import Path

from sqlalchemy import case, inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import db
from app.db.models import File, FileType

logger = logging.getLogger(__name__)

# Postgres caps bound parameters per statement at 65535 - stay comfortably
# under that regardless of how many columns a given model has.
MAX_QUERY_PARAMS = 65000


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


def _bulk_upsert(session, model, hash_column, values):
    if not values:
        return

    columns_per_row = len(values[0])
    chunk_size = max(1, MAX_QUERY_PARAMS // columns_per_row)

    for start in range(0, len(values), chunk_size):
        chunk = values[start:start + chunk_size]

        stmt = pg_insert(model).values(chunk)
        excluded = stmt.excluded
        min_col = getattr(model, 'min_extraction_date')
        max_col = getattr(model, 'max_extraction_date')

        stmt = stmt.on_conflict_do_update(
            index_elements=[hash_column],
            set_={
                'min_extraction_date': db.func.least(min_col, excluded.min_extraction_date),
                'max_extraction_date': db.func.greatest(max_col, excluded.max_extraction_date),
                'first_file_id': case(
                    (excluded.min_extraction_date < min_col, excluded.first_file_id),
                    else_=getattr(model, 'first_file_id'),
                ),
                'last_file_id': case(
                    (excluded.max_extraction_date > max_col, excluded.last_file_id),
                    else_=getattr(model, 'last_file_id'),
                ),
            },
        )
        session.execute(stmt)


def ingest_df(session, file, model, df):
    hash_column = inspect(model).primary_key[0].name
    file_id = file.file_id

    try:
        rows = df.to_dict(orient='records')
        rows = [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()} for row in rows]

        records = {}
        for row in rows:
            key = row[hash_column]

            extraction_date = row.pop('extraction_date')
            if hasattr(extraction_date, 'date'):
                extraction_date = extraction_date.date()
            row['min_extraction_date'] = extraction_date
            row['max_extraction_date'] = extraction_date
            row['first_file_id'] = file_id
            row['last_file_id'] = file_id

            existing = records.get(key)

            if existing is None:
                records[key] = row
                continue

            if row['min_extraction_date'] < existing['min_extraction_date']:
                existing['min_extraction_date'] = row['min_extraction_date']
                existing['first_file_id'] = row['first_file_id']

            if row['max_extraction_date'] > existing['max_extraction_date']:
                existing['max_extraction_date'] = row['max_extraction_date']
                existing['last_file_id'] = row['last_file_id']

        _bulk_upsert(session, model, hash_column, list(records.values()))

        file.loaded = datetime.now()
        session.add(file)
        session.commit()

        logger.info(f"Merged {len(records)} rows into {model.__tablename__}")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to insert into {model.__tablename__}: {e}")
