import gc
import logging
from datetime import datetime
from io import BytesIO

from app.db.models import FileType
from app.scraper.base import BaseScraper
from app.services.ingestion import get_or_create_file, ingest_df

logger = logging.getLogger(__name__)


class DailyScraper(BaseScraper):
    site = "https://www.mimit.gov.it"

    @classmethod
    def url_for(cls, file_type: FileType) -> str:
        return f"{cls.site}/images/exportCSV/{file_type.value}.csv"

    def run(self) -> bool:
        url = self.url_for(self.file_type)

        file = get_or_create_file(self.db, self.conn, url=url)

        if file.loaded:
            logger.info(f"Already loaded, skipping {url}")
            return False

        logger.info(f"Downloading {url}")

        response = self.conn.get(url)
        response.raise_for_status()

        extract = BytesIO(response.content)

        records = self.parse_csv(extract)
        if records:
            df = self.create_df(records)
            if df["extraction_date"].isna().all():
                df["extraction_date"] = datetime.now().date()
            ingest_df(session=self.db, file=file, model=self.model, df=df)
            del df, records

        file.loaded = datetime.now()
        self.db.add(file)
        self.db.commit()
        self.db.expunge_all()

        gc.collect()
        logger.info(f"Finished loading {url}")
        return True
