import json
import threading
from datetime import datetime, timedelta, timezone

from app.models import Booking, BookingStatus, Payment, PaymentStatus, WebhookEvent
from app.services import webhook_service
from tests.conftest import TestingSession


def send_webhook(client, event_id, provider_ref, status, signed=True):
    body = json.dumps({"event_id": event_id, "provider_ref": provider_ref, "status": status})
    headers = {"Content-Type": "application/json"}
    if signed:
        headers["X-Signature"] = webhook_service.compute_signature(body.encode())
    return client.post("/payments/webhook/", content=body, headers=headers)


def make_pending_payment(client, user_headers, offer, db):
    # a booking waiting for a payment result, like when the provider answers later
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    booking_id = client.post(
        "/bookings/",
        json={"test_id": offer["test_id"], "centre_id": offer["centre_id"], "appointment_time": when},
        headers=user_headers,
    ).json()["id"]
    payment = Payment(booking_id=booking_id, amount=500)
    db.add(payment)
    db.commit()
    return booking_id, payment.provider_ref


def booking_status(db, booking_id):
    db.expire_all()
    return db.get(Booking, booking_id).status


def test_success_webhook_confirms_booking(client, user_headers, offer, db):
    booking_id, ref = make_pending_payment(client, user_headers, offer, db)

    res = send_webhook(client, "evt_1", ref, "SUCCESS")

    assert res.status_code == 200
    assert res.json() == {"result": "processed"}
    assert booking_status(db, booking_id) == BookingStatus.CONFIRMED


def test_failed_webhook_fails_booking(client, user_headers, offer, db):
    booking_id, ref = make_pending_payment(client, user_headers, offer, db)
    send_webhook(client, "evt_1", ref, "FAILED")
    assert booking_status(db, booking_id) == BookingStatus.FAILED


def test_same_event_twice_changes_nothing_the_second_time(client, user_headers, offer, db):
    booking_id, ref = make_pending_payment(client, user_headers, offer, db)

    first = send_webhook(client, "evt_1", ref, "SUCCESS")
    second = send_webhook(client, "evt_1", ref, "SUCCESS")
    third = send_webhook(client, "evt_1", ref, "SUCCESS")

    assert first.json()["result"] == "processed"
    assert second.json()["result"] == "duplicate"
    assert third.json()["result"] == "duplicate"
    assert booking_status(db, booking_id) == BookingStatus.CONFIRMED
    assert db.query(Payment).count() == 1
    assert db.query(Booking).count() == 1
    assert db.query(WebhookEvent).count() == 1


def test_new_event_for_finished_payment_is_ignored(client, user_headers, offer, db):
    booking_id, ref = make_pending_payment(client, user_headers, offer, db)
    send_webhook(client, "evt_1", ref, "SUCCESS")

    # a different event that contradicts the first must not undo it
    res = send_webhook(client, "evt_2", ref, "FAILED")

    assert res.json()["result"] == "ignored"
    assert booking_status(db, booking_id) == BookingStatus.CONFIRMED
    db.expire_all()
    assert db.query(Payment).one().status == PaymentStatus.SUCCESS


def test_success_webhook_for_cancelled_booking_keeps_booking_cancelled(client, user_headers, offer, db):
    booking_id, ref = make_pending_payment(client, user_headers, offer, db)
    client.post(f"/bookings/{booking_id}/cancel", headers=user_headers)

    res = send_webhook(client, "evt_1", ref, "SUCCESS")

    assert res.status_code == 200
    assert booking_status(db, booking_id) == BookingStatus.CANCELLED
    db.expire_all()
    assert db.query(Payment).one().status == PaymentStatus.SUCCESS


def test_bad_or_missing_signature_is_rejected(client, user_headers, offer, db):
    booking_id, ref = make_pending_payment(client, user_headers, offer, db)

    assert send_webhook(client, "evt_1", ref, "SUCCESS", signed=False).status_code == 401
    res = client.post(
        "/payments/webhook/",
        content=json.dumps({"event_id": "evt_1", "provider_ref": ref, "status": "SUCCESS"}),
        headers={"X-Signature": "not-a-real-signature"},
    )
    assert res.status_code == 401
    assert booking_status(db, booking_id) == BookingStatus.PENDING
    assert db.query(WebhookEvent).count() == 0


def test_invalid_payloads_are_rejected(client):
    def signed_post(raw):
        return client.post(
            "/payments/webhook/",
            content=raw,
            headers={"X-Signature": webhook_service.compute_signature(raw.encode())},
        )

    assert signed_post("this is not json").status_code == 422
    assert signed_post('{"event_id": "e1"}').status_code == 422
    assert signed_post('{"event_id": "e1", "provider_ref": "x", "status": "MAYBE"}').status_code == 422
    assert signed_post('{"event_id": "e1", "provider_ref": "x", "status": "PENDING"}').status_code == 422


def test_unknown_payment_returns_404_and_event_is_kept_for_retry(client, db):
    res = send_webhook(client, "evt_1", "no-such-payment", "SUCCESS")

    assert res.status_code == 404
    event = db.query(WebhookEvent).one()
    assert event.processed is False
    assert event.attempts == 1


def test_retry_job_finishes_event_once_payment_exists(client, user_headers, offer, db):
    # the webhook arrives before we know the payment's reference
    booking_id, ref = make_pending_payment(client, user_headers, offer, db)
    send_webhook(client, "evt_1", "late-ref", "SUCCESS")
    payment = db.query(Payment).one()
    payment.provider_ref = "late-ref"
    db.commit()

    finished = webhook_service.retry_unprocessed(db)

    assert finished == 1
    assert booking_status(db, booking_id) == BookingStatus.CONFIRMED
    assert db.query(WebhookEvent).one().processed is True


def test_retry_job_gives_up_after_max_attempts(client, db):
    send_webhook(client, "evt_1", "never-exists", "SUCCESS")
    for _ in range(10):
        webhook_service.retry_unprocessed(db)

    assert db.query(WebhookEvent).one().attempts == webhook_service.MAX_ATTEMPTS


def test_parallel_duplicate_webhooks_apply_once(client, user_headers, offer, db):
    booking_id, ref = make_pending_payment(client, user_headers, offer, db)
    payload = {"event_id": "evt_race", "provider_ref": ref, "status": "SUCCESS"}
    results = []

    def worker():
        session = TestingSession()  # every thread gets its own DB session
        try:
            results.append(webhook_service.handle_webhook(session, "evt_race", payload))
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("processed") == 1
    assert set(results) <= {"processed", "duplicate", "ignored"}
    assert booking_status(db, booking_id) == BookingStatus.CONFIRMED
    assert db.query(WebhookEvent).count() == 1
    assert db.query(Payment).count() == 1
