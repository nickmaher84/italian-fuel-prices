from app.scraper.historic import HistoricScraper
from app.services.station_sync import StationSync
from app.db.models import FileType
import pandas as pd


def historic_scrape():
    for year, quarter in generate_quarters():
        for file_type in FileType:
            scraper = HistoricScraper(
                file_type=file_type,
                year=year,
                quarter=quarter,
            )
            loaded = scraper.run()

            if loaded and file_type == FileType.STATIONS:
                StationSync(scraper.db).run()


def generate_quarters(start="2015Q1"):
    end = pd.Period.now(freq='Q') - 1

    for period in pd.period_range(start=start, end=end, freq='Q'):
        yield period.year, period.quarter
