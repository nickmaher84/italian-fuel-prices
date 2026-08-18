from datetime import date

from sqlalchemy import bindparam
from sqlalchemy.dialects.postgresql import ARRAY

from app.core import db
from app.db.models import prices_daily as prices_daily_table


def prices_daily_query(start_date: date, end_date: date, station_ids: list[int] | None = None):
    station_ids_param = bindparam("station_ids", station_ids, type_=ARRAY(db.Integer))

    fn = db.func.prices_daily(start_date, end_date, station_ids_param).table_valued(
        *[c.name for c in prices_daily_table.columns]
    )

    return db.select(fn)
