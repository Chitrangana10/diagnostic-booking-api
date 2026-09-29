from datetime import datetime, timedelta, timezone

from app.models import Booking, BookingStatus


def future(days=2):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def book(client, headers, offer, when=None):
    return client.post(
        "/bookings/",
        json={
            "test_id": offer["test_id"],
            "centre_id": offer["centre_id"],
            "appointment_time": when or future(),
        },
        headers=headers,
    )


def test_create_booking_starts_pending_with_centre_price(client, user_headers, offer):
    res = book(client, user_headers, offer)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "PENDING"
    assert body["amount"] == "500.00"
    assert body["centre_name"] == "City Lab"
    assert body["test_name"] == "CBC"


def test_booking_requires_login(client, offer):
    res = client.post(
        "/bookings/",
        json={"test_id": 1, "centre_id": 1, "appointment_time": future()},
    )
    assert res.status_code in (401, 403)


def test_past_appointment_is_rejected(client, user_headers, offer):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert book(client, user_headers, offer, when=past).status_code == 400


def test_appointment_without_timezone_is_rejected(client, user_headers, offer):
    naive = (datetime.now() + timedelta(days=2)).replace(tzinfo=None).isoformat()
    assert book(client, user_headers, offer, when=naive).status_code == 422


def test_unknown_centre_or_test(client, user_headers, offer):
    body = {"test_id": offer["test_id"], "centre_id": 999, "appointment_time": future()}
    assert client.post("/bookings/", json=body, headers=user_headers).status_code == 404

    body = {"test_id": 999, "centre_id": offer["centre_id"], "appointment_time": future()}
    assert client.post("/bookings/", json=body, headers=user_headers).status_code == 404


def test_centre_must_offer_the_test(client, user_headers, offer, db):
    from app.models import DiagnosticTest

    other = DiagnosticTest(name="Lipid Profile")
    db.add(other)
    db.commit()
    body = {
        "test_id": other.id,
        "centre_id": offer["centre_id"],
        "appointment_time": future(),
    }
    assert client.post("/bookings/", json=body, headers=user_headers).status_code == 400


def test_list_shows_only_my_bookings(client, user_headers, other_user_headers, offer):
    book(client, user_headers, offer)
    book(client, other_user_headers, offer)

    mine = client.get("/bookings/", headers=user_headers).json()
    assert mine["total"] == 1


def test_cannot_see_someone_elses_booking(client, user_headers, other_user_headers, offer):
    booking_id = book(client, user_headers, offer).json()["id"]

    assert client.get(f"/bookings/{booking_id}", headers=user_headers).status_code == 200
    # 404, not 403, so ids can't be probed
    assert client.get(f"/bookings/{booking_id}", headers=other_user_headers).status_code == 404


def test_invalid_booking_id(client, user_headers):
    assert client.get("/bookings/99999", headers=user_headers).status_code == 404
    assert client.get("/bookings/abc", headers=user_headers).status_code == 422


def test_cancel_pending_booking(client, user_headers, offer):
    booking_id = book(client, user_headers, offer).json()["id"]
    res = client.post(f"/bookings/{booking_id}/cancel", headers=user_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "CANCELLED"


def test_cannot_cancel_twice(client, user_headers, offer):
    booking_id = book(client, user_headers, offer).json()["id"]
    client.post(f"/bookings/{booking_id}/cancel", headers=user_headers)
    res = client.post(f"/bookings/{booking_id}/cancel", headers=user_headers)
    assert res.status_code == 409


def test_cannot_cancel_someone_elses_booking(client, user_headers, other_user_headers, offer):
    booking_id = book(client, user_headers, offer).json()["id"]
    res = client.post(f"/bookings/{booking_id}/cancel", headers=other_user_headers)
    assert res.status_code == 404


def test_confirmed_booking_can_be_cancelled_but_failed_cannot(client, user_headers, offer, db):
    confirmed_id = book(client, user_headers, offer).json()["id"]
    failed_id = book(client, user_headers, offer).json()["id"]
    db.get(Booking, confirmed_id).status = BookingStatus.CONFIRMED
    db.get(Booking, failed_id).status = BookingStatus.FAILED
    db.commit()

    assert client.post(f"/bookings/{confirmed_id}/cancel", headers=user_headers).status_code == 200
    assert client.post(f"/bookings/{failed_id}/cancel", headers=user_headers).status_code == 409


def test_old_bookings_keep_their_price_after_price_change(client, user_headers, offer, db):
    from decimal import Decimal

    from app.models import CentreTest

    booking_id = book(client, user_headers, offer).json()["id"]
    ct = db.query(CentreTest).first()
    ct.price = Decimal("999.00")
    db.commit()

    assert client.get(f"/bookings/{booking_id}", headers=user_headers).json()["amount"] == "500.00"


def test_status_filter_and_pagination(client, user_headers, offer):
    first = book(client, user_headers, offer).json()["id"]
    book(client, user_headers, offer)
    client.post(f"/bookings/{first}/cancel", headers=user_headers)

    cancelled = client.get("/bookings/?status=CANCELLED", headers=user_headers).json()
    assert cancelled["total"] == 1
    page = client.get("/bookings/?size=1", headers=user_headers).json()
    assert len(page["items"]) == 1 and page["total"] == 2
    assert client.get("/bookings/?status=BOGUS", headers=user_headers).status_code == 422
