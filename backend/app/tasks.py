import pandas as pd
import redis

from app.celery_app import celery
from app.core import app as flask_app, db
from app.db.models import FileType
from app.scraper.historic import HistoricScraper
from app.services.station_sync import StationSync


class RedisFlag:
    """Thin get/set wrapper around a single Redis key used as an atomic present/absent flag."""
    url = flask_app.config['CELERY_BROKER_URL']

    def __init__(self, key: str):
        self.client = redis.Redis.from_url(self.url)
        self.key = key

    def get(self) -> bool:
        return bool(self.client.exists(self.key))

    def set(self) -> bool:
        """Atomically claim the flag. Returns True only if this call claimed it."""
        return bool(self.client.set(self.key, "1", nx=True))

    def clear(self) -> None:
        self.client.delete(self.key)


sync_stations_pending = RedisFlag("sync_stations:pending")


DEFAULT_START_QUARTER = pd.Period("2015Q1", freq='Q')


def latest_complete_quarter() -> pd.Period:
    return pd.Period.now(freq='Q') - 1


def generate_quarters(start: str | pd.Period = DEFAULT_START_QUARTER, end: str | pd.Period | None = None):
    end = pd.Period(end, freq='Q') if end else latest_complete_quarter()

    for period in pd.period_range(start=start, end=end, freq='Q'):
        yield period.year, period.quarter


@celery.task
def scrape_quarter_task(file_type_value: str, year: int, quarter: int) -> bool:
    file_type = FileType(file_type_value)
    scraper = HistoricScraper(file_type=file_type, year=year, quarter=quarter)
    loaded = scraper.run()

    if loaded and file_type == FileType.STATIONS:
        if sync_stations_pending.set():
            sync_stations_task.delay()

    return loaded


@celery.task
def sync_stations_task() -> None:
    try:
        StationSync(db.session).run()
    finally:
        sync_stations_pending.clear()


def _dispatch_scrapes(start: str | pd.Period = DEFAULT_START_QUARTER, end: str | pd.Period | None = None, file_types: list[str] | None = None):
    file_types = [FileType(t) for t in file_types] if file_types else list(FileType)

    for year, quarter in generate_quarters(start=start, end=end):
        for file_type in file_types:
            scrape_quarter_task.delay(file_type.value, year, quarter)


@celery.task
def historic_scrape_task():
    _dispatch_scrapes()


@celery.task
def scrape_range_task(start: str, end: str, file_types: list[str] | None = None):
    _dispatch_scrapes(start=start, end=end, file_types=file_types)


@celery.task
def poll_latest_quarter_task():
    period = latest_complete_quarter()
    year, quarter = period.year, period.quarter

    for file_type in FileType:
        if HistoricScraper(file_type, year, quarter).is_available():
            scrape_quarter_task.delay(file_type.value, year, quarter)
