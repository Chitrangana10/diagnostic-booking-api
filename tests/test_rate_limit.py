import pytest

from app.limiter import limiter


@pytest.fixture
def rate_limit_on():
    # the other tests run with the limiter off, so we switch it on only here
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


def test_login_is_limited_to_5_per_minute(client, rate_limit_on):
    body = {"email": "nobody@example.com", "password": "password123"}

    codes = [client.post("/auth/login", json=body).status_code for _ in range(7)]

    assert codes[:5] == [401] * 5  # wrong password, but still allowed through
    assert codes[5:] == [429, 429]  # then blocked


def test_other_endpoints_have_a_higher_limit(client, rate_limit_on):
    codes = {client.get("/centres/").status_code for _ in range(20)}
    assert codes == {200}
