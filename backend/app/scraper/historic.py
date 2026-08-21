import gc
import logging
import tarfile
from datetime import datetime
from io import BytesIO

import requests

from app.db.models import FileType
from app.scraper.base import BaseScraper
from app.services.ingestion import get_or_create_file, get_or_create_member, ingest_df

logger = logging.getLogger(__name__)


class HistoricScraper(BaseScraper):
    site = f"https://opendatacarburanti.mise.gov.it"

    def __init__(self, file_type: FileType, year: int, quarter: int):
        super().__init__(file_type)
        self.year = year
        self.quarter = quarter

    @classmethod
    def url_for(cls, file_type: FileType, year: int, quarter: int) -> str:
        return f"{cls.site}/categorized/{file_type.value}/{year}/{year}_{quarter}_tr.tar.gz"

    def is_available(self) -> bool:
        url = self.url_for(self.file_type, self.year, self.quarter)
        try:
            response = self.conn.head(url)
        except requests.RequestException as e:
            logger.warning(f"Availability check failed for {url}: {e}")
            return False

        if response.status_code != 200:
            logger.info(f"Not yet available ({response.status_code}): {url}")
            return False

        return True

    def run(self):
        url = self.url_for(self.file_type, self.year, self.quarter)

        file = get_or_create_file(self.db, self.conn, url=url)

        if file.loaded:
            logger.info(f"Already loaded, skipping {url}")
            return False

        file_obj = self.download_tar(url)

        with tarfile.open(fileobj=file_obj) as t:
            for member in t.getmembers():
                if member.isdir():
                    logger.info(f"Skipping {member.name}")
                    continue

                logger.info(f"Extracting {member.name}")
                m = get_or_create_member(self.db, member)

                if m.loaded:
                    logger.info(f"Already loaded, skipping {member.name}")
                    continue

                extract = t.extractfile(member)

                if member.size:
                    records = self.parse_csv(extract)
                    if records:
                        df = self.create_df(records)
                        if df["extraction_date"].isna().all():
                            df["extraction_date"] = m.file_date()
                        ingest_df(session=self.db, file=m, model=self.model, df=df)
                        del df, records

                m.loaded = datetime.now()
                self.db.add(m)
                self.db.commit()
                self.db.expunge_all()

        file.loaded = datetime.now()
        self.db.add(file)
        self.db.commit()
        self.db.expunge_all()

        self.vacuum()

        gc.collect()
        logger.info(f"Finished loading {url}")
        return True

    def download_tar(self, url:str):
        logger.info(f"Downloading {url}")

        response = self.conn.get(url)
        response.raise_for_status()

        return BytesIO(response.content)
