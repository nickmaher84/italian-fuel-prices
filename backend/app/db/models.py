from datetime import datetime, date
import uuid

from sqlalchemy.orm import Mapped, mapped_column

from app.core import db


class File(db.Model):
    file_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(db.String(255))
    extension: Mapped[str] = mapped_column(db.String(255))
    size: Mapped[int]
    checksum: Mapped[str] = mapped_column(db.String(255))
    modified: Mapped[datetime | None]
    loaded: Mapped[datetime | None]


class StationHistory(db.Model):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
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
    file_id: Mapped[uuid.UUID] = mapped_column()


class PriceHistory(db.Model):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    station_id: Mapped[int] = mapped_column(db.Integer)
    fuel_description: Mapped[str] = mapped_column(db.String(50))
    self_service: Mapped[bool] = mapped_column(db.Boolean)
    price: Mapped[float] = mapped_column(db.Numeric(9,3))
    entry_date: Mapped[datetime | None] = mapped_column(db.DateTime)
    extraction_date: Mapped[date | None]
    file_id: Mapped[uuid.UUID] = mapped_column()
