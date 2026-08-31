import logging
from datetime import datetime
from hashlib import md5
from html import unescape
from io import BytesIO

import pandas as pd
import requests

from app.core import db
from app.db.models import FileType

logger = logging.getLogger(__name__)


def to_bool(value: str) -> bool | None:
    try:
        return bool(int(value))
    except (ValueError, TypeError):
        return None

def to_datetime(value: str) -> datetime | None:
    if not isinstance(value, str):
        return None

    if "/" in value:
        formats = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y")
    else:
        formats = ("%Y-%m-%d %H:%M:%S", "%y-%m-%d", "%Y-%m-%d")

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return None


def safe_convert(converter):
    """Wrap a field converter so a single unparseable value yields None instead
    of aborting the whole file - source CSVs are occasionally corrupt (embedded
    NUL bytes, truncated or run-together rows) and we want to load every row we
    still can."""
    def convert(value):
        try:
            return converter(value)
        except (ValueError, TypeError):
            return None

    return convert

TAR_BLOCK = 512


def scrub_tar_debris(raw: bytes) -> bytes:
    """Strip slices of an uncompressed tar that disk corruption on the
    publisher's side has physically spliced into a source CSV. Exactly one file
    has ever been hit (2022-12-27; see docs/data-quality/2022-12-27-corruption),
    and only a file carrying NUL bytes can be affected, so this is a no-op for
    everything else.

    A tar header sits on a 512-byte boundary with the `ustar` magic at offset
    257 and is always followed by at least one record of member data. Drop every
    such header block and the block after it, then strip the NUL padding the
    splice left behind. Rows torn across a dropped boundary are left broken and
    get discarded downstream by _drop_unusable_rows."""
    if b"\x00" not in raw:
        return raw

    kept, drop_next = [], False
    for start in range(0, len(raw), TAR_BLOCK):
        block = raw[start:start + TAR_BLOCK]
        if drop_next:
            drop_next = False
            continue
        if block[257:262] == b"ustar":
            drop_next = True
            continue
        kept.append(block)

    scrubbed = b"".join(kept).replace(b"\x00", b"")
    if len(scrubbed) != len(raw):
        logger.warning(
            f"Scrubbed {len(raw) - len(scrubbed)} bytes of tar debris / NUL "
            f"padding from a corrupt source file"
        )
    return scrubbed


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


class BaseScraper:
    def __init__(self, file_type: FileType):
        self.db = db.session
        self.conn = requests.Session()
        self.file_type = file_type

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

    def vacuum(self):
        logger.debug(f"Vacuuming {self.model.__tablename__} now.")
        conn = db.engine.connect().execution_options(isolation_level='AUTOCOMMIT')
        try:
            conn.execute(db.text(f'VACUUM ANALYZE {self.model.__tablename__}'))
            logger.debug("Vacuuming complete.")
        finally:
            conn.close()

    def parse_csv(self, extract: BytesIO):
        csv_bytes = scrub_tar_debris(extract.read())
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

    def create_df(self, records: list[dict]):
        df = pd.DataFrame.from_records(records)
        df = df.replace(["NULL", ""], None)

        new_data = {}
        for col in df.columns:
            normalised = col.replace(' ', '').lower()
            if normalised in COLUMN_MAPPING:
                model_col, converter = COLUMN_MAPPING[normalised]
                data = df[col]
                if converter not in (int, str, float):
                    data = data.apply(safe_convert(converter))
                new_data[model_col] = data
            else:
                new_data[col] = df[col]

        df = pd.DataFrame(new_data)

        return self._drop_unusable_rows(df)

    @staticmethod
    def _drop_unusable_rows(df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows we can't key, price or date - a corrupt row (NUL bytes,
        merged or truncated fields) otherwise fails the bulk upsert and takes a
        whole chunk of good rows down with it. entry_date is NOT NULL, so a row
        whose timestamp wouldn't parse (safe_convert -> NaT) can't be inserted
        anyway. extraction_date is deliberately not checked here - HistoricScraper
        back-fills an all-NaT extraction_date column from the filename after
        create_df()."""
        numeric = [c for c in ("station_id", "price") if c in df.columns]
        dates = [c for c in ("entry_date",) if c in df.columns]
        if not numeric and not dates:
            return df

        before = len(df)

        for col in numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=numeric + dates)

        if "station_id" in df.columns:
            df["station_id"] = df["station_id"].astype(int)

        dropped = before - len(df)
        if dropped:
            logger.warning(f"Dropped {dropped} unparseable row(s) missing {' / '.join(numeric + dates)}")

        return df
