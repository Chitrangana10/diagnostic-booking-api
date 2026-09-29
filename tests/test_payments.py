from datetime import datetime, timedelta, timezone

from app.config import settings
from app.models import Booking


def make_booking(client, headers, offer):
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    res = client.post(
        "/bookings/",
        json={"test_id": offer["test_id"], "centre_id": offer["centre_id"], "appointment_time": when},
        headers=headers,
    )
    return res.json()["id"]


def pay(client, headers, booking_id, simulate=None):
    body = {"booking_id": booking_id}
    if simulate:
        body["simulate"] = simulate
    return client.post("/payments/", json=body, headers=headers)


def test_successful_payment_confirms_booking(client, user_headers, offer):
    booking_id = make_booking(client, user_headers, offer)
    res = pay(client, user_headers, booking_id, "SUCCESS")

    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "SUCCESS"
    assert body["booking_status"] == "CONFIRMED"
    assert body["amount"] == "500.00"
    assert client.get(f"/bookings/{booking_id}", headers=user_headers).json()["status"] == "CONFIRMED"


def test_failed_payment_marks_booking_failed(client, user_headers, offer):
    booking_id = make_booking(client, user_headers, offer)
    res = pay(client, user_headers, booking_id, "FAILED")

    assert res.json()["status"] == "FAILED"
    assert res.json()["booking_status"] == "FAILED"


def test_random_result_is_success_or_failed(client, user_headers, offer, monkeypatch):
    monkeypatch.setattr(settings, "payment_success_rate", 1.0)
    booking_id = make_booking(client, user_headers, offer)
    assert pay(client, user_headers, booking_id).json()["status"] == "SUCCESS"

    monkeypatch.setattr(settings, "payment_success_rate", 0.0)
    booking_id = make_booking(client, user_headers, offer)
    assert pay(client, user_headers, booking_id).json()["status"] == "FAILED"


def test_cannot_pay_twice(client, user_headers, offer):
    booking_id = make_booking(client, user_headers, offer)
    pay(client, user_headers, booking_id, "SUCCESS")
    assert pay(client, user_headers, booking_id, "SUCCESS").status_code == 409


def test_cannot_pay_for_failed_or_cancelled_booking(client, user_headers, offer):
    failed_id = make_booking(client, user_headers, offer)
    pay(client, user_headers, failed_id, "FAILED")
    assert pay(client, user_headers, failed_id, "SUCCESS").status_code == 409

    cancelled_id = make_booking(client, user_headers, offer)
    client.post(f"/bookings/{cancelled_id}/cancel", headers=user_headers)
    assert pay(client, user_headers, cancelled_id, "SUCCESS").status_code == 409


def test_cannot_pay_someone_elses_booking(client, user_headers, other_user_headers, offer, db):
    booking_id = make_booking(client, user_headers, offer)
    assert pay(client, other_user_headers, booking_id).status_code == 404
    assert db.get(Booking, booking_id).status.value == "PENDING"


def test_pay_unknown_booking(client, user_headers):
    assert pay(client, user_headers, 99999).status_code == 404


def test_payment_validation(client, user_headers, offer):
    assert client.post("/payments/", json={}, headers=user_headers).status_code == 422
    assert client.post("/payments/", json={"booking_id": "abc"}, headers=user_headers).status_code == 422
    booking_id = make_booking(client, user_headers, offer)
    assert pay(client, user_headers, booking_id, "MAYBE").status_code == 422


def test_payment_requires_login(client):
    assert client.post("/payments/", json={"booking_id": 1}).status_code in (401, 403)
