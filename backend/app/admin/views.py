from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView, expose
from flask import redirect, url_for
import app.db.models as m
from app.services.scrape import historic_scrape


class StandardModelView(ModelView):
    page_size = 50
    can_view_details = True
    column_display_pk = True


class ReadOnlyModelView(StandardModelView):
    can_create = False
    can_edit = False
    can_delete = False


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
        historic_scrape()

        return redirect(url_for(".index"))
