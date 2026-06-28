from flask import Blueprint
from flask_admin import Admin
from flask_admin.theme import Bootstrap4Theme

from app.admin.views import (
    StandardModelView,
    ReadOnlyModelView,
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
    )
    admin.add_view(StandardModelView(m.File, db.session))

    return admin
