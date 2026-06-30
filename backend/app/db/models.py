from datetime import datetime, date
import uuid

from sqlalchemy.orm import Mapped, mapped_column

from app.core import db


def to_bool(value: str) -> bool:
    return bool(int(value))

def to_float(value: str) -> float | None:
    if value == "NULL":
        return None
    return float(value)

def to_datetime(value: str) -> datetime | str:
    if value is None:
        return ""

    if "/" in value:
        try:
            return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            return datetime.strptime(value, "%d/%m/%Y")
    else:
        return datetime.strptime(value, "%Y-%m-%d")


class File(db.Model):
    file_id: Mapped[uuid.UUID] = mapped_column(db.UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(db.String(255))
    extension: Mapped[str] = mapped_column(db.String(255))
    size: Mapped[int]
    checksum: Mapped[str] = mapped_column(db.String(255))
    modified: Mapped[datetime | None]
    loaded: Mapped[datetime | None]


class StationHistory(db.Model):
    id: Mapped[uuid.UUID] = mapped_column(db.UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    station_id: Mapped[int] = mapped_column(db.Integer)
    station_name: Mapped[str] = mapped_column(db.String(100), nullable=True)
    station_type: Mapped[str] = mapped_column(db.String(20))
    operator_name: Mapped[str] = mapped_column(db.String(255), nullable=True)
    brand_name: Mapped[str] = mapped_column(db.String(50), nullable=True)
    address: Mapped[str] = mapped_column(db.String(255), nullable=True)
    comune: Mapped[str] = mapped_column(db.String(50), nullable=False)
    province_code: Mapped[str] = mapped_column(db.String(2), nullable=False)
    latitude: Mapped[float] = mapped_column(db.Float(), nullable=True)
    longitude: Mapped[float] = mapped_column(db.Float(), nullable=True)
    extraction_date: Mapped[date | None]
    file_id: Mapped[uuid.UUID] = mapped_column(db.UUID(as_uuid=False))

    column_mapping: dict[str, tuple[str, type]] = {
        "idimpianto": ("station_id", int),
        "nomeimpianto": ("station_name", str),
        "tipoimpianto": ("station_type", str),
        "gestore": ("operator_name", str),
        "bandiera": ("brand_name", str),
        "indirizzo": ("address", str),
        "comune": ("comune", str),
        "provincia": ("province_code", str),
        "latitudine": ("latitude", to_float),
        "longitudine": ("longitude", to_float),
        "extraction_date": ("extraction_date", to_datetime),
    }


class PriceHistory(db.Model):
    id: Mapped[uuid.UUID] = mapped_column(db.UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    station_id: Mapped[int] = mapped_column(db.Integer)
    fuel_description: Mapped[str] = mapped_column(db.String(50))
    self_service: Mapped[bool] = mapped_column(db.Boolean)
    price: Mapped[float] = mapped_column(db.Float)
    entry_date: Mapped[datetime | None] = mapped_column(db.DateTime)
    extraction_date: Mapped[date | None]
    file_id: Mapped[uuid.UUID] = mapped_column(db.UUID(as_uuid=False))

    column_mapping: dict[str, tuple[str, object]] = {
        "idimpianto": ("station_id", int),
        "desccarburante": ("fuel_description", str),
        "isself": ("self_service", to_bool),
        "prezzo": ("price", float),
        "dtcomu": ("entry_date", to_datetime),
        "extraction_date": ("extraction_date", to_datetime),
    }
