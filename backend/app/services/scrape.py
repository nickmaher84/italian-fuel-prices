from app.scraper.historic import HistoricScraper, FILE_TYPES
from datetime import date


def historic_scrape():
    for year, quarter in generate_quarters():
        for file_type in FILE_TYPES:
            scraper = HistoricScraper(
                file_type=file_type,
                year=year,
                quarter=quarter,
            )
            scraper.run()


def generate_quarters(since:int=2015):
    y = since
    q = 0

    today = date.today()
    end_year = today.year
    end_quarter = today.month // 3

    while not (y == end_year and q == end_quarter):
        q += 1
        if q > 4:
            y += 1
            q = 1
        yield y, q
