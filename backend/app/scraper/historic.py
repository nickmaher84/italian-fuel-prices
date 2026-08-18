import requests
import tarfile
import uuid
import pandas as pd
import gc
from io import BytesIO
from datetime import datetime
from html import unescape
from hashlib import md5

from app.core import db
from app.services.ingestion import get_or_create_file, get_or_create_member, ingest_df
from app.db.models import FileType

import logging

logger = logging.getLogger(__name__)


def to_bool(value: str) -> bool:
    return bool(int(value))

def to_datetime(value: str) -> datetime | None:
    if value is None:
        return value

    if "/" in value:
        try:
            return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            return datetime.strptime(value, "%d/%m/%Y")
    else:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(value, "%y-%m-%d")
            except ValueError:
                return datetime.strptime(value, "%Y-%m-%d")

def preprocess_line(values: list[str], delimiter: str, column_count: int) -> list[str]:
    values = [value.strip().strip('"') for value in values]

    for i in ["gestori.prezzibenzina.it", "BENZINA.IT", ""]:
        while i in values and len(values) > column_count:
            n = values.index(i)
            values[n-1] += f" {delimiter} " + values[n]
            del values[n]

    if len(values) > column_count:
        values[5] += values[6]
        del values[6]

    return values


COLUMN_MAPPING = {
    "idimpianto": ("station_id", int),
    "nomeimpianto": ("station_name", str),
    "tipoimpianto": ("station_type", str),
    "gestore": ("operator_name", str),
    "bandiera": ("brand_name", str),
    "indirizzo": ("address", str),
    "comune": ("comune", str),
    "provincia": ("province_code", str),
    "latitudine": ("latitude", float),
    "longitudine": ("longitude", float),
    "desccarburante": ("fuel_description", str),
    "isself": ("self_service", to_bool),
    "prezzo": ("price", float),
    "dtcomu": ("entry_date", to_datetime),
    "extraction_date": ("extraction_date", to_datetime),
}


class HistoricScraper:
    site = f"https://opendatacarburanti.mise.gov.it"

    def __init__(self, file_type:FileType, year:int, quarter:int):
        self.db = db.session
        self.conn = requests.Session()
        self.file_type = file_type
        self.year = year
        self.quarter = quarter

    @property
    def model(self):
        from app.db.models import PriceChange, StationChange

        model_map = {
            FileType.PRICES: PriceChange,
            FileType.STATIONS: StationChange,
        }

        return model_map[self.file_type]

    @property
    def hash_column(self):
        hash_column_map = {
            FileType.PRICES: "price_hash",
            FileType.STATIONS: "station_hash",
        }

        return hash_column_map[self.file_type]

    def run(self):
        url = f"{self.site}/categorized/{self.file_type.value}/{self.year}/{self.year}_{self.quarter}_tr.tar.gz"

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

    def vacuum(self):
        conn = db.engine.connect().execution_options(isolation_level='AUTOCOMMIT')
        try:
            conn.execute(db.text(f'VACUUM ANALYZE {self.model.__tablename__}'))
        finally:
            conn.close()

    def download_tar(self, url:str):
        logger.info(f"Downloading {url}")

        response = self.conn.get(url)
        response.raise_for_status()

        return BytesIO(response.content)

    def parse_csv(self, extract:BytesIO):
        csv_bytes = extract.read()
        text = csv_bytes.decode('utf-8')
        lines = text.split('\n')

        extraction_date = None
        header = None
        delimiter = ";"

        columns = []
        records = []

        for idx, line in enumerate(lines, 1):
            if line.startswith('Estrazione del'):
                extraction_date = line.strip()[-8:]
                logger.debug(f"Extraction date found on row {idx}: {extraction_date}")

            elif line.strip() and header is None:
                header = line
                logger.debug(f"Header found on row {idx}: {header}")
                delimiter: str = '|' if header.count('|') > header.count(';') else ';'
                logger.debug(f"File delimiter is {delimiter}")

                columns = header.split(delimiter)

            elif line.strip():
                line_hash = md5(line.encode('utf-8')).digest()
                fields = preprocess_line(unescape(line).split(delimiter), delimiter, len(columns))

                record = dict(zip(columns, fields))
                record[self.hash_column] = line_hash
                record['extraction_date'] = extraction_date
                records.append(record)

        if header is None:
            logger.error("No header row found. Skipping.")

        return records

    def create_df(self, records:list[dict]):
        df = pd.DataFrame.from_records(records)
        df = df.replace(["NULL", ""], None)

        new_data = {}
        for col in df.columns:
            normalised = col.replace(' ', '').lower()
            if normalised in COLUMN_MAPPING:
                model_col, converter = COLUMN_MAPPING[normalised]
                data = df[col]
                if converter not in (int, str, float):
                    data = data.apply(converter)
                new_data[model_col] = data
            else:
                new_data[col] = df[col]

        return pd.DataFrame(new_data)
