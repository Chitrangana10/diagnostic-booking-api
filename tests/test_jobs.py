from datetime import datetime, timedelta, timezone

from app.models import Booking, BookingStatus, Payment
from app.services import booking_service


def add_booking(db, offer, minutes_old):
    booking = Booking(
        user_id=1,
        centre_id=offer["centre_id"],
        test_id=offer["test_id"],
        appointment_time=datetime.now(timezone.utc) + timedelta(days=3),
        amount=500,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_old),
    )
    db.add(booking)
    db.commit()
    return booking


def test_old_pending_bookings_are_cancelled(client, user_headers, offer, db):
    old = add_booking(db, offer, minutes_old=45)
    fresh = add_booking(db, offer, minutes_old=5)

    cancelled = booking_service.expire_stale_bookings(db, older_than_minutes=30)

    assert cancelled == 1
    db.expire_all()
    assert db.get(Booking, old.id).status == BookingStatus.CANCELLED
    assert db.get(Booking, fresh.id).status == BookingStatus.PENDING


def test_booking_waiting_for_provider_is_not_expired(client, user_headers, offer, db):
    booking = add_booking(db, offer, minutes_old=45)
    db.add(Payment(booking_id=booking.id, amount=500))  # PENDING payment
    db.commit()

    assert booking_service.expire_stale_bookings(db, older_than_minutes=30) == 0


def test_confirmed_bookings_are_never_expired(client, user_headers, offer, db):
    booking = add_booking(db, offer, minutes_old=45)
    booking.status = BookingStatus.CONFIRMED
    db.commit()

    assert booking_service.expire_stale_bookings(db, older_than_minutes=30) == 0
