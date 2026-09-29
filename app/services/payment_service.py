import logging
import random

from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models import Booking, BookingStatus, Payment, PaymentStatus
from app.services import booking_service

logger = logging.getLogger(__name__)


def apply_result(db: Session, payment: Payment, result: PaymentStatus) -> bool:
    """Move a payment from PENDING to SUCCESS/FAILED and update its booking.

    Used by both POST /payments/ and the webhook. Returns False if the payment was
    already finished, in which case nothing is changed (this is what makes repeats safe).
    The caller commits.
    """
    if payment.status != PaymentStatus.PENDING:
        logger.info(
            "payment already finished, ignoring",
            extra={"payment_id": payment.id, "status": payment.status.value},
        )
        return False

    payment.status = result

    # lock the booking row so two requests can't change it at the same time
    booking = db.get(Booking, payment.booking_id, with_for_update=True)

    if booking.status != BookingStatus.PENDING:
        # e.g. user cancelled while the payment was in flight. The payment result is
        # still recorded, but we don't touch the booking.
        logger.warning(
            "payment finished for a booking that is not pending",
            extra={
                "payment_id": payment.id,
                "booking_id": booking.id,
                "booking_status": booking.status.value,
            },
        )
        return True

    if result == PaymentStatus.SUCCESS:
        booking_service.change_status(booking, BookingStatus.CONFIRMED)
    else:
        booking_service.change_status(booking, BookingStatus.FAILED)
    return True


def make_payment(
    db: Session, user_id: int, booking_id: int, force: PaymentStatus | None = None
) -> tuple[Payment, Booking]:
    # lock first, so a double click can't create two payments for one booking
    booking = db.get(Booking, booking_id, with_for_update=True)
    if booking is None or booking.user_id != user_id:
        raise AppError(404, "Booking not found")
    if booking.status != BookingStatus.PENDING:
        raise AppError(409, f"Booking is {booking.status.value}, it cannot be paid")

    payment = Payment(booking_id=booking.id, amount=booking.amount)
    db.add(payment)
    db.flush()  # gives the payment an id and provider_ref

    # this is the "fake payment provider": pick a result at random unless told otherwise
    if force is not None:
        result = force
    elif random.random() < settings.payment_success_rate:
        result = PaymentStatus.SUCCESS
    else:
        result = PaymentStatus.FAILED

    apply_result(db, payment, result)
    db.commit()
    logger.info(
        "payment processed",
        extra={"payment_id": payment.id, "booking_id": booking.id, "result": result.value},
    )
    return payment, booking
