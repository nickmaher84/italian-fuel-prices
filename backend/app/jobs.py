import logging
from datetime import datetime

from celery.signals import task_prerun, task_postrun, task_failure

from app.core import app as flask_app, db
from app.db.models import JobRun

logger = logging.getLogger(__name__)


@task_prerun.connect
def _on_task_prerun(task_id, task, args, kwargs, **_):
    with flask_app.app_context():
        db.session.add(JobRun(
            task_id=task_id,
            task_name=task.name,
            args=repr(args) if args else None,
            status='STARTED',
            started=datetime.now(),
        ))
        db.session.commit()


@task_postrun.connect
def _on_task_postrun(task_id, task, retval, state, **_):
    with flask_app.app_context():
        run = _get_by_task_id(task_id)
        if run is None:
            return

        run.status = state
        run.finished = datetime.now()
        db.session.commit()


@task_failure.connect
def _on_task_failure(task_id, exception, **_):
    with flask_app.app_context():
        run = _get_by_task_id(task_id)
        if run is None:
            return

        run.status = 'FAILURE'
        run.error = str(exception)
        run.finished = datetime.now()
        db.session.commit()


def _get_by_task_id(task_id):
    return db.session.scalar(db.select(JobRun).where(JobRun.task_id == task_id))
