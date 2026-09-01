import json
import logging
from datetime import date, datetime, timezone

import redis

from app.celery_app import celery
from app.core import app as flask_app, db
from app.db.models import FileType
from app.quarters import DEFAULT_START_QUARTER, generate_quarters, latest_complete_quarter, quarter_date_range
from app.scraper.daily import DailyScraper
from app.scraper.historic import HistoricScraper
from app.services.mirror import Mirror
from app.services.station_sync import StationSync
from app.services.price_sync import PriceSync

logger = logging.getLogger(__name__)


class RedisFlag:
    """Thin get/set wrapper around a single Redis key used as an atomic present/absent flag."""
    url = flask_app.config['CELERY_BROKER_URL']

    def __init__(self, key: str):
        self.client = redis.Redis.from_url(self.url)
        self.key = key

    def get(self) -> bool:
        return bool(self.client.exists(self.key))

    def set(self, ttl: int | None = None) -> bool:
        """Atomically claim the flag. Returns True only if this call claimed it.
        Pass ttl (seconds) so the flag self-clears if the holder dies without
        running its finally block - e.g. a task killed by the OOM killer."""
        return bool(self.client.set(self.key, "1", nx=True, ex=ttl))

    def clear(self) -> None:
        self.client.delete(self.key)


class RedisValue:
    """Thin wrapper around a single Redis key holding a string - used to leave a
    breadcrumb (e.g. the outcome of the last mirror rebuild) that the admin
    dashboard can read."""
    url = flask_app.config['CELERY_BROKER_URL']

    def __init__(self, key: str):
        self.client = redis.Redis.from_url(self.url)
        self.key = key

    def get(self) -> str | None:
        value = self.client.get(self.key)
        return value.decode() if value is not None else None

    def set(self, value: str, ttl: int | None = None) -> None:
        self.client.set(self.key, value, ex=ttl)


sync_stations_pending = RedisFlag("sync_stations:pending")
mirror_rebuild_pending = RedisFlag("mirror_rebuild:pending")
mirror_rebuild_result = RedisValue("mirror_rebuild:last_result")


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
        sync = StationSync(db.session)
        sync.run()
    finally:
        sync_stations_pending.clear()


@celery.task
def sync_prices_task(start_date: str, end_date: str) -> None:
    sync = PriceSync()
    sync.run(
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
    )


@celery.task
def rebuild_mirror_task() -> None:
    """Discard the mirror file and rebuild every table from Postgres. Long
    running (~1 hour) and, with worker_concurrency=1, holds the worker for its
    duration. Guarded by mirror_rebuild_pending so a double click is a no-op;
    records its outcome in mirror_rebuild_result for the dashboard."""
    outcome = {"status": "failure", "detail": "did not finish", "at": None}
    try:
        Mirror().rebuild()
        outcome = {"status": "success", "detail": "", "at": _utc_now()}
    except Exception as e:
        logger.exception("mirror rebuild failed")
        outcome = {"status": "failure", "detail": f"{type(e).__name__}: {e}"[:400], "at": _utc_now()}
        raise
    finally:
        mirror_rebuild_pending.clear()
        try:
            mirror_rebuild_result.set(json.dumps(outcome), ttl=30 * 24 * 3600)
        except Exception:
            logger.exception("could not record mirror rebuild outcome")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


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
