import logging

from app.config import settings
from app.database import SessionLocal
from app.services import booking_service, webhook_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def retry_failed_webhooks():
    with SessionLocal() as db:
        done = webhook_service.retry_unprocessed(db)
    logger.info("webhook retry job finished", extra={"finished": done})
    return done


@celery_app.task
def expire_pending_bookings():
    with SessionLocal() as db:
        cancelled = booking_service.expire_stale_bookings(db, settings.pending_booking_minutes)
    logger.info("expiry job finished", extra={"cancelled": cancelled})
    return cancelled
