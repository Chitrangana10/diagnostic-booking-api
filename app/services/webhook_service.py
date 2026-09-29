import hashlib
import hmac
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models import Payment, PaymentStatus, WebhookEvent
from app.services import payment_service

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


def compute_signature(body: bytes) -> str:
    return hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(compute_signature(body), signature)


def process_event(db: Session, event: WebhookEvent) -> str:
    """Apply one stored event to its payment. Returns "processed" or "ignored"."""
    event.attempts += 1

    payment = db.scalar(
        select(Payment)
        .where(Payment.provider_ref == event.payload["provider_ref"])
        .with_for_update()
    )
    if payment is None:
        db.commit()  # keep the attempt count
        raise AppError(404, "Unknown payment")

    applied = payment_service.apply_result(
        db, payment, PaymentStatus(event.payload["status"])
    )
    event.processed = True
    db.commit()
    return "processed" if applied else "ignored"


def handle_webhook(db: Session, event_id: str, payload: dict) -> str:
    """Store the event, then process it. Safe to call many times with the same event_id."""
    event = WebhookEvent(event_id=event_id, payload=payload)
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # we have seen this event_id before
        db.rollback()
        event = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
        if event.processed:
            logger.info("duplicate webhook ignored", extra={"event_id": event_id})
            return "duplicate"
        # seen before but never finished (earlier attempt failed), so try again

    return process_event(db, event)


def retry_unprocessed(db: Session) -> int:
    """Used by the background job: re-run events that failed earlier. Returns how many finished."""
    events = db.scalars(
        select(WebhookEvent).where(
            WebhookEvent.processed.is_(False), WebhookEvent.attempts < MAX_ATTEMPTS
        )
    ).all()

    done = 0
    for event in events:
        try:
            process_event(db, event)
            done += 1
        except AppError as exc:
            logger.warning(
                "webhook retry failed",
                extra={"event_id": event.event_id, "reason": exc.detail},
            )
    return done
