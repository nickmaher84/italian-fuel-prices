from datetime import date

import redis

from app.celery_app import celery
from app.core import app as flask_app, db
from app.db.models import FileType
from app.quarters import DEFAULT_START_QUARTER, generate_quarters, latest_complete_quarter, quarter_date_range
from app.scraper.daily import DailyScraper
from app.scraper.historic import HistoricScraper
from app.services.station_sync import StationSync
from app.services.price_sync import PriceSync


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


def run_daily_scrape():
    today = date.today()
    for file_type in FileType:
        loaded = DailyScraper(file_type).run()

        if loaded and file_type == FileType.STATIONS:
            if sync_stations_pending.set():
                sync_stations_task.delay()

        if loaded and file_type == FileType.PRICES:
            sync_prices_task.delay(
                today.isoformat(),
                today.isoformat(),
            )


@celery.task
def scrape_daily_task():
    run_daily_scrape()


@celery.task
def scrape_quarter_task(file_type_value: str, year: int, quarter: int) -> bool:
    file_type = FileType(file_type_value)
    scraper = HistoricScraper(file_type=file_type, year=year, quarter=quarter)
    loaded = scraper.run()

    if loaded and file_type == FileType.STATIONS:
        if sync_stations_pending.set():
            sync_stations_task.delay()

    if loaded and file_type == FileType.PRICES:
        start, end = quarter_date_range(year, quarter)
        sync_prices_task.delay(
            start.isoformat(),
            end.isoformat(),
        )

    return loaded


@celery.task
def sync_stations_task() -> None:
    try:
        StationSync(db.session).run()
    finally:
        sync_stations_pending.clear()


@celery.task
def sync_prices_task(start_date: str, end_date: str) -> None:
    sync = PriceSync()
    sync.run(
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
    )


def _dispatch_scrapes(start: str = str(DEFAULT_START_QUARTER), end: str | None = None, file_types: list[str] | None = None):
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
