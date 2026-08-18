from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView, BaseView, expose
from flask import redirect, url_for, flash, request
import app.db.models as m
from app.services.scrape import historic_scrape
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
