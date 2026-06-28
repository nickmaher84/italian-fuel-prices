from flask_admin.contrib.sqla import ModelView


class StandardModelView(ModelView):
    page_size = 50
    can_view_details = True
    column_display_pk = True


class ReadOnlyModelView(StandardModelView):
    can_create = False
    can_edit = False
    can_delete = False
