import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Booking, BookingStatus, CentreTest, DiagnosticCentre, DiagnosticTest

logger = logging.getLogger(__name__)

# status -> statuses it is allowed to move to. Anything not listed here is rejected.
ALLOWED_TRANSITIONS = {
    BookingStatus.PENDING: {
        BookingStatus.CONFIRMED,
        BookingStatus.FAILED,
        BookingStatus.CANCELLED,
    },
    BookingStatus.CONFIRMED: {BookingStatus.CANCELLED},
    BookingStatus.FAILED: set(),
    BookingStatus.CANCELLED: set(),
}


def change_status(booking: Booking, new_status: BookingStatus) -> None:
    """The only place that is allowed to change booking.status."""
    if new_status not in ALLOWED_TRANSITIONS[booking.status]:
        raise AppError(
            409, f"Booking is {booking.status.value}, it cannot become {new_status.value}"
        )
    logger.info(
        "booking status changed",
        extra={"booking_id": booking.id, "old": booking.status.value, "new": new_status.value},
    )
    booking.status = new_status


def create_booking(
    db: Session, user_id: int, test_id: int, centre_id: int, appointment_time: datetime
) -> Booking:
    if appointment_time <= datetime.now(timezone.utc):
        raise AppError(400, "Appointment time must be in the future")

    if db.get(DiagnosticCentre, centre_id) is None:
        raise AppError(404, "Centre not found")
    if db.get(DiagnosticTest, test_id) is None:
        raise AppError(404, "Test not found")

    offer = db.scalar(
        select(CentreTest).where(
            CentreTest.centre_id == centre_id, CentreTest.test_id == test_id
        )
    )
    if offer is None:
        raise AppError(400, "This centre does not offer this test")

    booking = Booking(
        user_id=user_id,
        centre_id=centre_id,
        test_id=test_id,
        appointment_time=appointment_time,
        amount=offer.price,  # price is frozen at booking time
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    logger.info("booking created", extra={"booking_id": booking.id, "user_id": user_id})
    return booking


def get_user_booking(db: Session, booking_id: int, user_id: int) -> Booking:
    booking = db.get(Booking, booking_id)
    # someone else's booking looks exactly like a missing one, so ids can't be probed
    if booking is None or booking.user_id != user_id:
        raise AppError(404, "Booking not found")
    return booking


def cancel_booking(db: Session, booking_id: int, user_id: int) -> Booking:
    booking = get_user_booking(db, booking_id, user_id)
    change_status(booking, BookingStatus.CANCELLED)
    db.commit()
    return booking
