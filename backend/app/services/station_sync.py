import logging

from app.core import db
from app.db.models import Station, StationChange

logger = logging.getLogger(__name__)


class StationSync:
    def __init__(self, session: db.Session):
        self.session = session

    def run(self, incremental: bool = True):
        logger.info("Running station sync...")

        max_existing_date = None
        if incremental:
            max_existing_date = self.session.execute(
                db.select(db.func.max(Station.extraction_date))
            ).scalar()

            if max_existing_date:
                logger.info(f"Considering changes since {max_existing_date}")

        row_num = db.func.row_number().over(
            partition_by=StationChange.station_id,
            order_by=StationChange.max_extraction_date.desc()
        ).label('rn')

        stmt = db.select(StationChange, row_num)

        if max_existing_date:
            stmt = stmt.where(StationChange.max_extraction_date > max_existing_date)

        records = self.session.execute(stmt).all()
        current = [record for record, rn in records if rn == 1]
        logger.info(f"Found {len(current)} stations to sync")

        if not current:
            return

        station_ids = [record.station_id for record in current]
        existing_stations = {
            station.station_id: station
            for station in self.session.scalars(
                db.select(Station).where(Station.station_id.in_(station_ids))
            )
        }

        for record in current:
            station = existing_stations.get(record.station_id)

            if station is None:
                station = Station(station_id=record.station_id)
                self.session.add(station)

            station.station_name = record.station_name
            station.station_type = record.station_type
            station.operator_name = record.operator_name
            station.brand_name = record.brand_name
            station.address = record.address
            station.comune = record.comune
            station.province_code = record.province_code
            station.latitude = record.latitude
            station.longitude = record.longitude
            station.extraction_date = record.max_extraction_date
            station.file_id = record.last_file_id

            if station.comune:
                station.comune = station.comune.upper()

        self.session.commit()
        logger.info(f"Synced {len(current)} stations")
