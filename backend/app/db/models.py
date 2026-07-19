import enum
from datetime import datetime, date
import uuid
import re

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Index, ForeignKey, ForeignKeyConstraint

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


class StationHistory(db.Model):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
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
    extraction_date: Mapped[date] = mapped_column(primary_key=True)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('file.file_id'))

    __table_args__ = (
        ForeignKeyConstraint(['file_id'], ['file.file_id'], name='fk_station_history_file_id'),
        Index('idx_station_history_file_id', 'file_id'),
        Index('idx_station_history_extraction_date', 'extraction_date'),
        {'info': {'partition_by': 'RANGE (extraction_date)'}},
    )


class PriceHistory(db.Model):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    station_id: Mapped[int] = mapped_column(db.Integer)
    fuel_description: Mapped[str] = mapped_column(db.String(50))
    self_service: Mapped[bool] = mapped_column(db.Boolean)
    price: Mapped[float] = mapped_column(db.Numeric(9,3))
    entry_date: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=False)
    extraction_date: Mapped[date | None] = mapped_column(primary_key=True)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('file.file_id'))

    __table_args__ = (
        ForeignKeyConstraint(['file_id'], ['file.file_id'], name='fk_price_history_file_id'),
        Index('idx_price_history_file_id', 'file_id'),
        Index('idx_price_history_extraction_date', 'extraction_date'),
        {'info': {'partition_by': 'RANGE (extraction_date)'}},
    )


class ParserError(db.Model):
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('file.file_id'), primary_key=True)
    line_number: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    line: Mapped[str] = mapped_column(db.Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    __table_args__ = (
        ForeignKeyConstraint(['file_id'], ['file.file_id'], name='fk_parser_error_file_id'),
        Index('idx_parser_error_file_id', 'file_id'),
    )
