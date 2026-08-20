import pandas as pd
from celery import chain

from app.celery_app import celery
from app.core import db
from app.db.models import FileType
from app.scraper.historic import HistoricScraper
from app.services.station_sync import StationSync

DEFAULT_START_QUARTER = pd.Period("2015Q1", freq='Q')


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


def _build_scrape_chain(start: str | pd.Period = DEFAULT_START_QUARTER, end: str | pd.Period | None = None, file_types: list[str] | None = None):
    """Build (but don't submit) a chain covering the given quarter range/file-types, in order.

    Chained so each step only starts once the previous one finishes - this
    keeps writes to station_change/price_change strictly sequential, which
    matters given the lock contention and vacuum/bloat issues concurrent
    writers caused during earlier backfills. Sync is chained (not fired off
    in parallel) for the same reason, immediately after its station quarter.

    HistoricScraper.run() already skips quarters that are fully loaded, so
    re-queuing this over already-loaded history is inexpensive.
    """
    types = [FileType(t) for t in file_types] if file_types else list(FileType)

    steps = []
    for year, quarter in generate_quarters(start=start, end=end):
        for file_type in types:
            steps.append(scrape_quarter_task.si(file_type.value, year, quarter))

            if file_type == FileType.STATIONS:
                steps.append(sync_stations_task.s())

    return chain(*steps)


@celery.task
def historic_scrape_task():
    """Queue the full-history chain, from 2015Q1 up to the last complete quarter."""
    _build_scrape_chain().apply_async()


@celery.task
def scrape_range_task(start: str, end: str, file_types: list[str] | None = None):
    """Queue a chain for a specific quarter range, optionally limited to given file types.

    For ad hoc/test runs - e.g. scrape_range_task.delay("2017Q2", "2017Q2", ["anagrafica_impianti_attivi"])
    to load just stations for Q2 2017.
    """
    _build_scrape_chain(start=start, end=end, file_types=file_types).apply_async()


def generate_quarters(start: str | pd.Period = DEFAULT_START_QUARTER, end: str | pd.Period | None = None):
    end = pd.Period(end, freq='Q') if end else pd.Period.now(freq='Q') - 1

    for period in pd.period_range(start=start, end=end, freq='Q'):
        yield period.year, period.quarter
