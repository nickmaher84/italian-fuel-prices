import requests
from datetime import date
from werkzeug.http import parse_date
from hashlib import md5

from app.core import db
from app.db.models import File

import logging

logger = logging.getLogger(__name__)


class HistoricScraper:
    PRICES   = "prezzo_alle_8"
    STATIONS = "anagrafica_impianti_attivi"

    FILE_TYPES = {
        PRICES: "Prices",
        STATIONS: "Stations",
    }

    def __init__(self, since:int=2015):
        self.db = db.session
        self.conn = requests.Session()
        self.quarters = self.generate_quarters(since)

    @staticmethod
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

    def retrieve_tar_file(self, file_type:str, year:int, quarter:int):
        url = f"https://opendatacarburanti.mise.gov.it/categorized/{file_type}/{year}/{year}_{quarter}_tr.tar.gz"

        head_response = self.conn.head(url)
        head_response.raise_for_status()
        etag = head_response.headers.get('ETag', '').strip('"')

        existing = self.db.scalar(
            db.select(File).filter_by(filename=url, checksum=etag)
        )
        if existing is not None and existing.loaded is not None:
            logger.info(f"Tar file already loaded, skipping {url}")
            return

        if existing is not None and existing.loaded is None:
            logger.info(f"Seen before {url} but not loaded, re-downloading to retry")

        response = self.conn.get(url)
        logger.info(f"{response.status_code} {response.url} {len(response.content)}")
        response.raise_for_status()

        if existing is None:
            file = File(
                filename=response.url,
                extension=response.url.split(".")[-1],
                size=len(response.content),
                checksum=etag,
                modified=parse_date(response.headers.get("Last-Modified")),
            )
            self.db.add(file)
            self.db.commit()


    def run(self):
        for year, quarter in self.quarters:
            for file_type in self.FILE_TYPES:
                self.retrieve_tar_file(file_type, year, quarter)
