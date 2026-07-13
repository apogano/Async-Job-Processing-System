from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "async_job_system",
    broker= settings.redis_url,
    backend= settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_default_retry_delay=5,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "cleanup-stale-jobs-every-15-minutes": {
            "task": "cleanup_stale_jobs",
            "schedule": crontab(minute="*/15"),
            "kwargs": {"stale_after_minutes": 60},
        },
    },   
)
