from flask import Blueprint
from flask_admin import Admin
from flask_admin.theme import Bootstrap4Theme

from app.admin.views import (
    FileModelView,
    AdminView,
    StationModelView,
    StationChangeModelView,
    PriceChangeModelView,
)
from app.core import db
import app.db.models as m


def init_admin(app):
    template_bp = Blueprint("admin_templates", __name__, template_folder="templates")
    app.register_blueprint(template_bp)

    admin = Admin(
        app,
        name="Fuel Price Admin",
        url="/admin",
        theme=Bootstrap4Theme(swatch="flatly"),
        index_view=AdminView(),
    )
    admin.add_view(FileModelView(m.File, db.session))
    admin.add_view(StationModelView(m.Station, db.session, name="Stations", category="Stations"))
    admin.add_view(StationChangeModelView(m.StationChange, db.session, name="Station Changes", category="Stations"))
    admin.add_view(PriceChangeModelView(m.PriceChange, db.session, name="Price Changes", category="Prices"))

    return admin
