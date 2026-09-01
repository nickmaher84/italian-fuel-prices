from datetime import date

import pandas as pd

DEFAULT_START_QUARTER = pd.Period("2015Q1", freq='Q')


def latest_complete_quarter() -> pd.Period:
    return pd.Period.now(freq='Q') - 1


def generate_quarters(start: str | pd.Period = DEFAULT_START_QUARTER, end: str | pd.Period | None = None):
    end = pd.Period(end, freq='Q') if end else latest_complete_quarter()

    for period in pd.period_range(start=start, end=end, freq='Q'):
        yield period.year, period.quarter


def quarter_date_range(year: int, quarter: int) -> tuple[date, date]:
    period = pd.Period(f"{year}Q{quarter}", freq='Q')
    return period.start_time.date(), period.end_time.date()


def quarter_chunks(start: date | None = None, end: date | None = None) -> list[tuple[date, date]]:
    start_period = pd.Period(start, freq='Q') if start else DEFAULT_START_QUARTER
    end_period = pd.Period(end, freq='Q') if end else pd.Period.now(freq='Q')

    ranges = []
    for period in pd.period_range(start=start_period, end=end_period, freq='Q'):
        chunk_start = period.start_time.date()
        chunk_end = period.end_time.date()
        if start and chunk_start < start:
            chunk_start = start
        if end and chunk_end > end:
            chunk_end = end
        ranges.append((chunk_start, chunk_end))
    return ranges
