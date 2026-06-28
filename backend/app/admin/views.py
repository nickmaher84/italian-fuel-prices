from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView, expose
import app.db.models as m


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
        return self.render(
            "index.html",
            files=files,
        )
