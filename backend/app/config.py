import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'development'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///fuel-prices.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False


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
