import logging
import math
from datetime import datetime
from werkzeug.http import parse_date
from pathlib import Path

from sqlalchemy import inspect

from app.core import db
from app.db.models import File, FileType

logger = logging.getLogger(__name__)


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

        pk_attr = getattr(model, hash_column)
        existing_instances = {
            getattr(instance, hash_column): instance
            for instance in session.scalars(
                db.select(model).where(pk_attr.in_(records.keys()))
            )
        }

        for key, row in records.items():
            instance = existing_instances.get(key)

            if instance is None:
                instance = model(**row)
                session.add(instance)

            elif row['min_extraction_date'] < instance.min_extraction_date:
                instance.min_extraction_date = row['min_extraction_date']
                instance.first_file_id = row['first_file_id']

            elif row['max_extraction_date'] > instance.max_extraction_date:
                instance.max_extraction_date = row['max_extraction_date']
                instance.last_file_id = row['last_file_id']

        file.loaded = datetime.now()
        session.add(file)
        session.commit()

        logger.info(f"Merged {len(records)} rows into {model.__tablename__}")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to insert into {model.__tablename__}: {e}")
