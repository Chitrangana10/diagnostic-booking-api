from types import SimpleNamespace

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
    token = create_access_token(SimpleNamespace(id=9999, token_version=0))
    res = client.get("/bookings/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def login_tokens(client):
    client.post("/auth/signup", json=SIGNUP)
    res = client.post(
        "/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    return res.json()


def test_login_gives_access_and_refresh_token(client):
    tokens = login_tokens(client)
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["access_token"] != tokens["refresh_token"]


def test_refresh_gives_a_working_new_access_token(client):
    tokens = login_tokens(client)
    res = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 200

    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/bookings/", headers=headers).status_code == 200


def test_access_token_cannot_be_used_as_refresh_token(client):
    tokens = login_tokens(client)
    res = client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert res.status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client):
    tokens = login_tokens(client)
    headers = {"Authorization": f"Bearer {tokens['refresh_token']}"}
    assert client.get("/bookings/", headers=headers).status_code == 401


def test_garbage_refresh_token_is_rejected(client):
    res = client.post("/auth/refresh", json={"refresh_token": "garbage"})
    assert res.status_code == 401


def test_logout_kills_existing_tokens(client):
    tokens = login_tokens(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get("/bookings/", headers=headers).status_code == 200

    assert client.post("/auth/logout", headers=headers).status_code == 204

    # the old access token and the old refresh token are both dead now
    assert client.get("/bookings/", headers=headers).status_code == 401
    res = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 401


def test_logout_requires_login(client):
    assert client.post("/auth/logout").status_code == 401


def test_can_log_in_again_after_logout(client):
    tokens = login_tokens(client)
    client.post("/auth/logout", headers={"Authorization": f"Bearer {tokens['access_token']}"})

    res = client.post(
        "/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/bookings/", headers=headers).status_code == 200
