from datetime import date, datetime, timedelta

from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView, BaseView, expose
from flask import redirect, url_for, flash, request
import app.db.models as m
from app.services.scrape import historic_scrape
from app.services.prices import prices_daily_query
from app.core import db



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


class JobRunModelView(ReadOnlyModelView):
    column_default_sort = ("started", True)
    column_filters = ["task_name", "status", "started"]


class PricesDailyView(BaseView):
    MAX_PRICES_DAILY_RANGE = timedelta(days=31)
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
                    stmt = prices_daily_query(start, end, [int(station_id)])
                    rows = db.session.execute(stmt).all()

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
    @expose("/")
    def index(self):
        files = m.File.query.count()
        stations = m.Station.query.count()
        prices = approx_count(m.PriceChange)

        return self.render(
            "index.html",
            files=files,
            stations=stations,
            prices=prices,
        )

    @expose("/scrape", methods=["POST"])
    def scrape(self):
        try:
            historic_scrape()
            flash("Scrape successful", category="success")
        except Exception as e:
            flash(str(e), "error")

        return redirect(url_for(".index"))


def approx_count(model: db.Model):
    query = db.text("SELECT reltuples::bigint FROM pg_class WHERE relname = :table_name")
    return db.session.execute(query, {"table_name": model.__tablename__}).scalar()
