from celery import Celery
from celery.schedules import crontab

from app.core import app as flask_app

celery = Celery(
    flask_app.import_name,
    broker=flask_app.config['CELERY_BROKER_URL'],
    backend=flask_app.config['CELERY_RESULT_BACKEND'],
)
celery.conf.update(
    task_track_started=True,
    result_extended=True,
    timezone='Europe/Rome',
    worker_concurrency=1,
    beat_schedule={
        'poll-latest-quarter': {
            'task': 'app.tasks.poll_latest_quarter_task',
            'schedule': crontab(hour=6, minute=0),
        },
        'scrape-daily-files': {
            'task': 'app.tasks.scrape_daily_task',
            'schedule': crontab(hour='9,21', minute=0),
        },
    },
)


class FlaskTask(celery.Task):
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)


celery.Task = FlaskTask

import app.jobs  # noqa: E402  (registers signal handlers as a side effect of import)
import app.tasks  # noqa: E402  (registers tasks as a side effect of import)
