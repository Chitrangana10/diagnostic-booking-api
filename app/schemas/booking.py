from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel

from app.models import BookingStatus


class BookingCreate(BaseModel):
    test_id: int
    centre_id: int
    # must include a timezone, e.g. 2026-10-20T10:00:00+05:30
    appointment_time: AwareDatetime


class BookingOut(BaseModel):
    id: int
    test_id: int
    test_name: str
    centre_id: int
    centre_name: str
    appointment_time: datetime
    amount: Decimal
    status: BookingStatus
    created_at: datetime


def booking_to_out(booking) -> BookingOut:
    return BookingOut(
        id=booking.id,
        test_id=booking.test_id,
        test_name=booking.test.name,
        centre_id=booking.centre_id,
        centre_name=booking.centre.name,
        appointment_time=booking.appointment_time,
        amount=booking.amount,
        status=booking.status,
        created_at=booking.created_at,
    )
