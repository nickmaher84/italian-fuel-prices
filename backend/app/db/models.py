from datetime import datetime
import uuid

from sqlalchemy.orm import Mapped, mapped_column

from app.core import db


class File(db.Model):
    file_id: Mapped[str] = mapped_column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(db.String(255))
    extension: Mapped[str] = mapped_column(db.String(255))
    size: Mapped[int]
    checksum: Mapped[str] = mapped_column(db.String(255))
    modified: Mapped[datetime | None]
    loaded: Mapped[datetime | None]
