import logging
from datetime import datetime
from werkzeug.http import parse_date

from app.core import db
from app.db.models import File

logger = logging.getLogger(__name__)


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
        extension=response.url.split(".")[-1],
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
        db.select(File).filter_by(filename=member.name, checksum=checksum)
    )

    if existing:
        return existing

    file = File(
        filename=member.name,
        extension=member.name.split(".")[-1],
        checksum=checksum,
        modified=modified,
        size=size,
    )

    session.add(file)
    session.commit()

    return file


def ingest_df(session, file, model, df):
    session.query(model).filter(model.file_id == file.file_id).delete()
    session.commit()

    table_name = model.__tablename__
    df = df[list(model.__table__.columns.keys())]

    duckdb_conn = session.connection().connection
    data = duckdb_conn.from_df(df)
    try:
        data.insert_into(table_name)
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to insert into {table_name}: {e}")
        raise

    file.loaded = datetime.now()
    session.add(file)
    session.commit()

    logger.info(f"Inserted {len(df)} rows into {table_name}")
