import pandas as pd
from celery import chain

from app.celery_app import celery
from app.core import db
from app.db.models import FileType
from app.scraper.historic import HistoricScraper
from app.services.station_sync import StationSync


@celery.task
def scrape_quarter_task(file_type_value: str, year: int, quarter: int) -> bool:
    scraper = HistoricScraper(
        file_type=FileType(file_type_value),
        year=year,
        quarter=quarter,
    )
    return scraper.run()


@celery.task
def sync_stations_task(loaded: bool = True) -> None:
    if not loaded:
        return

    StationSync(db.session).run()


@celery.task
def historic_scrape_task():
    """Queue a chain covering every quarter/file-type, in order.

    Chained so each step only starts once the previous one finishes - this
    keeps writes to station_change/price_change strictly sequential, which
    matters given the lock contention and vacuum/bloat issues concurrent
    writers caused during earlier backfills. Sync is chained (not fired off
    in parallel) for the same reason, immediately after its station quarter.

    HistoricScraper.run() already skips quarters that are fully loaded, so
    re-queuing this over already-loaded history is inexpensive.
    """
    steps = []

    for year, quarter in generate_quarters():
        for file_type in FileType:
            steps.append(scrape_quarter_task.si(file_type.value, year, quarter))

            if file_type == FileType.STATIONS:
                steps.append(sync_stations_task.s())

    chain(*steps).apply_async()


def generate_quarters(start="2015Q1"):
    end = pd.Period.now(freq='Q') - 1

    for period in pd.period_range(start=start, end=end, freq='Q'):
        yield period.year, period.quarter
