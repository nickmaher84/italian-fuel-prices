import logging
import math
from datetime import datetime
from werkzeug.http import parse_date
from pathlib import Path

from app.core import db
from app.db.models import File, ParserError

logger = logging.getLogger(__name__)


def get_extension(filename):
    path = Path(filename)
    return ''.join(path.suffixes)


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
    )

    session.add(file)
    session.commit()

    return file


def ingest_df(session, file, model, df):
    session.query(model).filter(model.file_id == file.file_id).delete()

    try:
        rows = df.to_dict(orient='records')
        rows = [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()} for row in rows]
        session.bulk_insert_mappings(model, rows)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to insert into {model.__tablename__}: {e}")
        raise

    file.loaded = datetime.now()
    session.add(file)
    session.commit()

    logger.info(f"Inserted {len(df)} rows into {model.__tablename__}")


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
