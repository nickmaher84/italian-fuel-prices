import logging
from datetime import date

from app.services.mirror import Mirror

logger = logging.getLogger(__name__)


class PriceSync:
    def __init__(self, mirror: Mirror | None = None):
        self.mirror = mirror or Mirror()

    def run(self, start_date: date, end_date: date) -> None:
        logger.info(f"Running prices sync for {start_date} to {end_date}...")

        count = self.mirror.sync_price_range(start_date, end_date)

        logger.info(f"Price sync finished - upserted {count} rows")
