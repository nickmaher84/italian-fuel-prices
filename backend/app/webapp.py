from app.core import app
from app.admin.setup import init_admin

init_admin(app)


if __name__ == '__main__':
    app.run(port=8080, debug=True)
