import requests
import tarfile
from io import BytesIO
from datetime import date, datetime
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

        existing_tar = self.db.scalar(
            db.select(File).filter_by(filename=url, checksum=etag)
        )
        if existing_tar is not None and existing_tar.loaded is not None:
            logger.info(f"Tar file already loaded, skipping {url}")
            return

        if existing_tar is not None and existing_tar.loaded is None:
            logger.info(f"Seen before {url} but not loaded, re-downloading to retry")

        response = self.conn.get(url)
        logger.info(f"{response.status_code} {response.url} {len(response.content)}")
        response.raise_for_status()

        if existing_tar is None:
            tar_file = File(
                filename=response.url,
                extension=response.url.split(".")[-1],
                size=len(response.content),
                checksum=etag,
                modified=parse_date(response.headers.get("Last-Modified")),
            )
            self.db.add(tar_file)
            self.db.commit()

        content = BytesIO(response.content)
        with tarfile.open(fileobj=content) as tar:
            for member in tar.getmembers():
                logger.info(f"Extracting {member.name}")
                csv_content = tar.extractfile(member)
                csv_bytes = csv_content.read()

                csv_checksum = md5(csv_bytes).hexdigest()
                csv_filename = f"{response.url}/{member.name}"

                existing_csv = self.db.scalar(
                    db.select(File).filter_by(filename=csv_filename, checksum=csv_checksum)
                )
                if existing_csv is not None:
                    if existing_csv.loaded is not None:
                        logger.info(f"Already loaded {member.name}, skipping")
                    else:
                        logger.info(f"Seen before {member.name}, will retry loading")
                    continue

                csv_file = File(
                    filename=csv_filename,
                    extension=member.name.split(".")[-1],
                    size=member.size,
                    checksum=csv_checksum,
                    modified=datetime.fromtimestamp(member.mtime),
                )

                self.db.add(csv_file)
                self.db.commit()


    def run(self):
        for year, quarter in self.quarters:
            for file_type in self.FILE_TYPES:
                self.retrieve_tar_file(file_type, year, quarter)
