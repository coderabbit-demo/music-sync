from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "music_sync",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.sync_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_soft_time_limit=1800,   # 30 min per task
    task_time_limit=2100,        # hard kill at 35 min
    beat_schedule={
        "scheduled-sync-all": {
            "task": "app.tasks.sync_tasks.scheduled_sync_all",
            "schedule": 900.0,   # every 15 minutes
        },
    },
)
