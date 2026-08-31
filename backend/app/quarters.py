import pandas as pd

DEFAULT_START_QUARTER = pd.Period("2015Q1", freq='Q')


def latest_complete_quarter() -> pd.Period:
    return pd.Period.now(freq='Q') - 1


def generate_quarters(start: str | pd.Period = DEFAULT_START_QUARTER, end: str | pd.Period | None = None):
    end = pd.Period(end, freq='Q') if end else latest_complete_quarter()

    for period in pd.period_range(start=start, end=end, freq='Q'):
        yield period.year, period.quarter
