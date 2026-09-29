from app.security import create_access_token

SIGNUP = {"name": "Asha", "email": "asha@example.com", "password": "password123"}


def test_signup_creates_user(client):
    res = client.post("/auth/signup", json=SIGNUP)
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "asha@example.com"
    assert "password" not in body and "password_hash" not in body


def test_signup_duplicate_email_is_rejected(client):
    client.post("/auth/signup", json=SIGNUP)
    res = client.post("/auth/signup", json={**SIGNUP, "email": "ASHA@example.com"})
    assert res.status_code == 409


def test_signup_validates_input(client):
    assert client.post("/auth/signup", json={**SIGNUP, "email": "nope"}).status_code == 422
    assert client.post("/auth/signup", json={**SIGNUP, "password": "short"}).status_code == 422
    assert client.post("/auth/signup", json={"email": "a@b.com"}).status_code == 422


def test_login_returns_token(client):
    client.post("/auth/signup", json=SIGNUP)
    res = client.post(
        "/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_login_wrong_password(client):
    client.post("/auth/signup", json=SIGNUP)
    res = client.post("/auth/login", json={"email": SIGNUP["email"], "password": "wrongpass1"})
    assert res.status_code == 401


def test_login_unknown_email(client):
    res = client.post("/auth/login", json={"email": "who@example.com", "password": "password123"})
    assert res.status_code == 401


def test_protected_route_needs_valid_token(client):
    # /bookings/ is protected; no header -> rejected, garbage token -> rejected
    assert client.get("/bookings/").status_code in (401, 403)
    res = client.get("/bookings/", headers={"Authorization": "Bearer garbage"})
    assert res.status_code == 401


def test_token_for_deleted_user_is_rejected(client):
    token = create_access_token(user_id=9999)
    res = client.get("/bookings/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
