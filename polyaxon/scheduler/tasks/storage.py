import logging

import stores

from polyaxon.celery_api import celery_app
from polyaxon.settings import SchedulerCeleryTasks

_logger = logging.getLogger(__name__)


@celery_app.task(name=SchedulerCeleryTasks.STORES_SCHEDULE_DATA_DELETION, ignore_result=True)
def stores_schedule_data_deletion(persistence, subpath):
    stores.delete_data_path(persistence=persistence, subpath=subpath)


@celery_app.task(name=SchedulerCeleryTasks.STORES_SCHEDULE_OUTPUTS_DELETION, ignore_result=True)
def stores_schedule_outputs_deletion(persistence, subpath):
    stores.delete_outputs_path(persistence=persistence, subpath=subpath)


@celery_app.task(name=SchedulerCeleryTasks.STORES_SCHEDULE_LOGS_DELETION, ignore_result=True)
def stores_schedule_logs_deletion(persistence, subpath):
    stores.delete_logs_path(persistence=persistence, subpath=subpath)
