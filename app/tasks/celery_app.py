from celery import Celery

from app.config import settings
from app.logging_config import setup_logging

setup_logging()

celery_app = Celery("eve", broker=settings.redis_url, include=["app.tasks.jobs"])

# celery beat runs these on a timer
celery_app.conf.beat_schedule = {
    "retry-failed-webhooks": {
        "task": "app.tasks.jobs.retry_failed_webhooks",
        "schedule": 60.0,  # every minute
    },
    "expire-pending-bookings": {
        "task": "app.tasks.jobs.expire_pending_bookings",
        "schedule": 300.0,  # every 5 minutes
    },
}

# keep our json logging instead of celery's own log setup
celery_app.conf.worker_hijack_root_logger = False
