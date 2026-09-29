from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Booking, BookingStatus, User
from app.schemas.booking import BookingCreate, BookingOut, booking_to_out
from app.schemas.common import Page
from app.services import booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    data: BookingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = booking_service.create_booking(
        db, user.id, data.test_id, data.centre_id, data.appointment_time
    )
    return booking_to_out(booking)


@router.get("/", response_model=Page[BookingOut])
def list_my_bookings(
    status_filter: BookingStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(Booking).where(Booking.user_id == user.id)
    if status_filter:
        query = query.where(Booking.status == status_filter)

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    bookings = db.scalars(
        query.options(selectinload(Booking.test), selectinload(Booking.centre))
        .order_by(Booking.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return Page(
        items=[booking_to_out(b) for b in bookings], total=total, page=page, size=size
    )


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return booking_to_out(booking_service.get_user_booking(db, booking_id, user.id))


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return booking_to_out(booking_service.cancel_booking(db, booking_id, user.id))
