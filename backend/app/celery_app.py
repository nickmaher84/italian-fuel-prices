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
    # Different quarters' hash-keyed writes don't need to run in order, but
    # concurrent writers to station_change/price_change on this host caused
    # real lock contention and vacuum/bloat issues during earlier backfills
    # - pinning this in config (rather than relying on always remembering to
    # pass --concurrency=1 on the command line) is what actually keeps that
    # from happening again.
    worker_concurrency=1,
    beat_schedule={
        'poll-latest-quarter': {
            'task': 'app.tasks.poll_latest_quarter_task',
            'schedule': crontab(hour=6, minute=0),
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
