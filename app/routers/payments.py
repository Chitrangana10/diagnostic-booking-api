from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.errors import AppError
from app.models import PaymentStatus, User
from app.schemas.payment import PaymentCreate, PaymentOut, WebhookPayload, WebhookResult
from app.services import payment_service, webhook_service

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment(
    data: PaymentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fake payment: ends in SUCCESS or FAILED and updates the booking to match."""
    payment, booking = payment_service.make_payment(
        db, user.id, data.booking_id, force=data.simulate
    )
    return PaymentOut(
        id=payment.id,
        booking_id=payment.booking_id,
        amount=payment.amount,
        status=payment.status,
        provider_ref=payment.provider_ref,
        booking_status=booking.status,
    )


@router.post("/webhook/", response_model=WebhookResult)
async def payment_webhook(
    request: Request,
    x_signature: str | None = Header(None, description="HMAC-SHA256 of the raw body"),
    db: Session = Depends(get_db),
):
    """Called by the payment provider. Sending the same event_id again is harmless."""
    # the signature is computed over the exact bytes, so we read the raw body
    body = await request.body()
    if not webhook_service.verify_signature(body, x_signature):
        raise AppError(401, "Invalid webhook signature")

    try:
        payload = WebhookPayload.model_validate_json(body)
    except ValidationError as exc:
        raise AppError(422, f"Invalid webhook payload: {exc.errors()[0]['msg']}")
    if payload.status == PaymentStatus.PENDING:
        raise AppError(422, "Webhook status must be SUCCESS or FAILED")

    result = webhook_service.handle_webhook(db, payload.event_id, payload.model_dump(mode="json"))
    return WebhookResult(result=result)
