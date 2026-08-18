import enum
from datetime import datetime, date
import uuid
import re

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey

from app.core import db


class FileType(enum.Enum):
    PRICES = "prezzo_alle_8"
    STATIONS = "anagrafica_impianti_attivi"


class File(db.Model):
    file_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(db.String(255))
    extension: Mapped[str] = mapped_column(db.String(255))
    size: Mapped[int]
    file_type: Mapped[FileType | None] = mapped_column(db.Enum(FileType, name="file_type"), nullable=True)
    checksum: Mapped[str] = mapped_column(db.String(255))
    modified: Mapped[datetime | None]
    loaded: Mapped[datetime | None]

    def file_date(self) -> date | None:
        match = re.search(r'(\d{4})(\d{2})(\d{2})', self.filename)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            return date(year, month, day)
        return None

    def quarter(self) -> str | None:
        file_date = self.file_date()
        if file_date:
            year = file_date.year
            month = file_date.month
            quarter = (month - 1) // 3 + 1
            return f"{year}Q{quarter}"
        return None


class StationChange(db.Model):
    station_hash: Mapped[bytes] = mapped_column(db.LargeBinary(16), primary_key=True)
    station_id: Mapped[int] = mapped_column(db.Integer)
    station_name: Mapped[str] = mapped_column(db.String(100), nullable=True)
    station_type: Mapped[str] = mapped_column(db.String(20))
    operator_name: Mapped[str] = mapped_column(db.String(255), nullable=True)
    brand_name: Mapped[str] = mapped_column(db.String(50), nullable=True)
    address: Mapped[str] = mapped_column(db.String(255), nullable=True)
    comune: Mapped[str] = mapped_column(db.String(50), nullable=True)
    province_code: Mapped[str] = mapped_column(db.String(2), nullable=True)
    latitude: Mapped[float] = mapped_column(db.Float(), nullable=True)
    longitude: Mapped[float] = mapped_column(db.Float(), nullable=True)

    min_extraction_date: Mapped[date] = mapped_column()
    max_extraction_date: Mapped[date] = mapped_column()
    first_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('file.file_id'))
    last_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('file.file_id'))


class PriceChange(db.Model):
    price_hash: Mapped[bytes] = mapped_column(db.LargeBinary(16), primary_key=True)
    station_id: Mapped[int] = mapped_column(db.Integer)
    fuel_description: Mapped[str] = mapped_column(db.String(50))
    self_service: Mapped[bool] = mapped_column(db.Boolean)
    price: Mapped[float] = mapped_column(db.Numeric(9, 3))
    entry_date: Mapped[datetime] = mapped_column(db.DateTime)

    min_extraction_date: Mapped[date] = mapped_column()
    max_extraction_date: Mapped[date] = mapped_column()
    first_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('file.file_id'))
    last_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('file.file_id'))
