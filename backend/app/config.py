import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_HOST = os.environ.get('DATABASE_HOST') or 'localhost'
DATABASE_PORT = int(os.environ.get('DATABASE_PORT') or 5432)
DATABASE_NAME = os.environ.get('DATABASE_NAME') or 'fuel-prices'
DATABASE_USERNAME = os.environ.get('DATABASE_USERNAME')
DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'development'

    SQLALCHEMY_DATABASE_URI = URL.create(
        drivername='postgresql+psycopg2',
        host=DATABASE_HOST,
        port=DATABASE_PORT,
        database=DATABASE_NAME,
        username=DATABASE_USERNAME,
        password=DATABASE_PASSWORD,
    ).render_as_string(hide_password=False)

    PG_ATTACH_URI = URL.create(
        drivername='postgresql',
        host=DATABASE_HOST,
        port=DATABASE_PORT,
        database=DATABASE_NAME,
        username=DATABASE_USERNAME,
        password=DATABASE_PASSWORD,
    ).render_as_string(hide_password=False)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'executemany_mode': 'values_plus_batch',
    }

    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0'

    MIRROR_PATH = Path(os.environ['MIRROR_PATH']) if os.environ.get('MIRROR_PATH') else BASE_DIR / 'mirror.duckdb'
    MIRROR_MEMORY_LIMIT = os.environ.get('MIRROR_MEMORY_LIMIT')


LOGGING = {
    'version': 1,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s in %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
    },
    'loggers': {
        'alembic': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
        'alembic.runtime.migration': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
    },
    'root': {
        'level': os.environ.get('LOG_LEVEL', 'INFO'),
        'handlers': ['console'],
    },
}
