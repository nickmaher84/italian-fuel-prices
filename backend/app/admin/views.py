from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView, expose
from flask import redirect, url_for, flash
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


class FileModelView(StandardModelView):
    can_create = False
    can_edit = False
    column_filters = ["file_type", "extension", "filename"]

    def delete_model(self, model):
        try:
            file_id = model.file_id
            m.StationHistory.query.filter_by(file_id=file_id).delete()
            m.PriceHistory.query.filter_by(file_id=file_id).delete()
            db.session.delete(model)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise


class StationHistoryModelView(ReadOnlyModelView):
    column_filters = ["station_id", "extraction_date", "comune", "province_code", "brand_name", "operator_name"]


class PriceHistoryModelView(ReadOnlyModelView):
    column_filters = ["station_id", "extraction_date", "fuel_description", "self_service"]

class AdminView(AdminIndexView):
    @expose("/")
    def index(self):
        files = m.File.query.count()
        stations = m.StationHistory.query.count()
        prices = m.PriceHistory.query.count()
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
