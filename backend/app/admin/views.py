import json
from datetime import date, datetime, timedelta

from collections import namedtuple
from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView, BaseView, expose
from flask import redirect, url_for, flash, request
import app.db.models as m
from app.db.models import FileType
from app.tasks import (
    historic_scrape_task,
    scrape_range_task,
    run_daily_scrape,
    rebuild_mirror_task,
    mirror_rebuild_pending,
    mirror_rebuild_result,
)
from app.quarters import DEFAULT_START_QUARTER, generate_quarters, latest_complete_quarter
from app.services.mirror import Mirror
from app.celery_app import celery
from app.core import db


def quarter_choices() -> list[str]:
    quarters = [f"{year}Q{quarter}" for year, quarter in generate_quarters(start=DEFAULT_START_QUARTER, end=latest_complete_quarter())]
    quarters.reverse()
    return quarters



class StandardModelView(ModelView):
    page_size = 50
    can_view_details = True
    column_display_pk = True


class ReadOnlyModelView(StandardModelView):
    can_create = False
    can_edit = False
    can_delete = False


class FileModelView(ReadOnlyModelView):
    column_filters = ["file_type", "extension", "filename"]


class StationModelView(ReadOnlyModelView):
    column_filters = ["station_id", "extraction_date", "comune", "province_code", "brand_name", "operator_name"]


class StationChangeModelView(ReadOnlyModelView):
    column_filters = ["station_id", "min_extraction_date", "max_extraction_date", "comune", "province_code", "brand_name", "operator_name"]


class PriceChangeModelView(ReadOnlyModelView):
    column_filters = ["station_id", "min_extraction_date", "max_extraction_date", "fuel_description", "self_service"]


class PricesDailyView(BaseView):
    MAX_PRICES_DAILY_RANGE = timedelta(weeks=52)
    MIN_START_DATE = date(2015, 1, 1)

    @expose("/")
    def index(self):
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        station_id = request.args.get("station_id")
        fuel_description = request.args.get("fuel_description")
        self_service = request.args.get("self_service")

        rows = None
        error = None

        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                end = datetime.strptime(end_date, "%Y-%m-%d").date()

                if not station_id:
                    error = "Station ID is required."
                elif start < self.MIN_START_DATE:
                    error = "Start date must not be before 2015."
                elif end < start:
                    error = "End date must not be before start date."
                elif end - start > self.MAX_PRICES_DAILY_RANGE:
                    error = f"Range too large - please request at most {self.MAX_PRICES_DAILY_RANGE.days} days at a time."
                else:
                    mirror = Mirror()
                    records = mirror.prices_daily(start, end, [int(station_id)])

                    PricesDailyRow = namedtuple(
                        "PricesDailyRow",
                        ["price_date", "station_id", "fuel_description", "self_service", "price", "entry_date", "price_hash"],
                    )
                    rows = [PricesDailyRow(*row) for row in records]

                    if fuel_description:
                        needle = fuel_description.lower()
                        rows = [r for r in rows if needle in r.fuel_description.lower()]

                    if self_service:
                        rows = [r for r in rows if r.self_service == (self_service == "true")]

            except ValueError:
                error = "Please enter valid dates (YYYY-MM-DD) and a numeric station ID."

        return self.render(
            "prices_daily.html",
            start_date=start_date,
            end_date=end_date,
            station_id=station_id,
            fuel_description=fuel_description,
            self_service=self_service,
            rows=rows,
            error=error,
        )


class AdminView(AdminIndexView):
    INSPECT_TIMEOUT = 2.0

    @expose("/")
    def index(self):
        files = m.File.query.count()
        stations = m.Station.query.count()
        prices = approx_count(m.PriceChange)

        queue_rows, worker_online = self._queue_snapshot()

        try:
            rebuild_pending = mirror_rebuild_pending.get()
            raw_result = mirror_rebuild_result.get()
            rebuild_result = json.loads(raw_result) if raw_result else None
        except Exception:
            rebuild_pending = False
            rebuild_result = None

        return self.render(
            "index.html",
            files=files,
            stations=stations,
            prices=prices,
            file_types=FileType,
            quarters=quarter_choices(),
            queue_rows=queue_rows,
            worker_online=worker_online,
            mirror_rebuild_pending=rebuild_pending,
            mirror_rebuild_result=rebuild_result,
        )

    @expose("/scrape", methods=["POST"])
    def scrape(self):
        try:
            historic_scrape_task.delay()
            flash("Historical backfill queued", category="success")
        except Exception as e:
            flash(str(e), "error")

        return redirect(url_for(".index"))

    @expose("/scrape-daily", methods=["POST"])
    def scrape_daily(self):
        try:
            run_daily_scrape()
            flash("Daily scrape complete", category="success")
        except Exception as e:
            flash(str(e), "error")

        return redirect(url_for(".index"))

    @expose("/rebuild-mirror", methods=["POST"])
    def rebuild_mirror(self):
        try:
            if mirror_rebuild_pending.set(ttl=3 * 60 * 60):
                rebuild_mirror_task.delay()
                flash("Mirror rebuild queued - runs in the background for ~1 hour.", "success")
            else:
                flash("A mirror rebuild is already queued or running.", "warning")
        except Exception as e:
            flash(str(e), "error")

        return redirect(url_for(".index"))

    @expose("/scrape-range", methods=["POST"])
    def scrape_range(self):
        start = request.form.get("start_quarter", "").strip().upper()
        end = request.form.get("end_quarter", "").strip().upper()
        file_types = request.form.getlist("file_types")
        choices = quarter_choices()

        if start not in choices or end not in choices:
            flash("Please select valid start and end quarters.", "error")
        elif end < start:
            flash("End quarter must not be before start quarter.", "error")
        else:
            scrape_range_task.delay(start, end, file_types or None)
            flash(f"Scrape queued for {start} to {end}", "success")

        return redirect(url_for(".index"))

    def _queue_snapshot(self):
        inspect = celery.control.inspect(timeout=self.INSPECT_TIMEOUT)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        scheduled = inspect.scheduled() or {}
        worker_online = bool(active or reserved or scheduled or inspect.ping())

        def flatten(by_worker, kind):
            rows = []
            for worker, tasks in by_worker.items():
                for t in tasks:
                    request = t.get("request", t)
                    rows.append({
                        "worker": worker,
                        "kind": kind,
                        "name": request.get("name"),
                        "args": request.get("args"),
                        "id": request.get("id"),
                    })
            return rows

        rows = flatten(active, "active") + flatten(reserved, "reserved") + flatten(scheduled, "scheduled")

        # A message that's been redelivered without being acked can show up
        # repeatedly under the same id - dedupe so the page reflects distinct
        # tasks, not delivery attempts.
        seen = set()
        deduped = []
        for row in rows:
            key = (row["kind"], row["id"])
            if key not in seen:
                seen.add(key)
                deduped.append(row)

        return deduped, worker_online


def approx_count(model: db.Model):
    query = db.text("SELECT reltuples::bigint FROM pg_class WHERE relname = :table_name")
    return db.session.execute(query, {"table_name": model.__tablename__}).scalar()
