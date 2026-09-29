from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import BookingStatus, PaymentStatus


class PaymentCreate(BaseModel):
    booking_id: int
    # only for the fake provider: lets tests/demos force an outcome. Leave empty for random.
    simulate: PaymentStatus | None = Field(
        default=None, description="Force SUCCESS or FAILED. Leave empty for a random result."
    )


class PaymentOut(BaseModel):
    id: int
    booking_id: int
    amount: Decimal
    status: PaymentStatus
    provider_ref: str
    booking_status: BookingStatus


class WebhookPayload(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    provider_ref: str = Field(min_length=1, max_length=64)
    status: PaymentStatus


class WebhookResult(BaseModel):
    result: str
