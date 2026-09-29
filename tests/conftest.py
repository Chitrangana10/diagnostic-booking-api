import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import cache, models  # noqa: F401
from app.database import Base, get_db
from app.limiter import limiter
from app.main import app
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest, User
from app.security import hash_password

# tests use their own database so they never touch real data
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://eve:eve@localhost:5432/eve_test"
)

engine = create_engine(TEST_DATABASE_URL)
TestingSession = sessionmaker(bind=engine, autoflush=False)

limiter.enabled = False


@pytest.fixture(autouse=True)
def fresh_tables():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    cache.delete_prefix("centres:")  # cached pages from an earlier test would be stale
    yield


@pytest.fixture
def db():
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def signup_and_login(client, email="user@example.com", name="Test User"):
    password = "password123"
    client.post(
        "/auth/signup", json={"name": name, "email": email, "password": password}
    )
    res = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def user_headers(client):
    return signup_and_login(client)


@pytest.fixture
def other_user_headers(client):
    return signup_and_login(client, email="other@example.com", name="Other User")


@pytest.fixture
def admin_headers(client, db):
    db.add(
        User(
            name="Admin",
            email="admin@example.com",
            password_hash=hash_password("password123"),
            is_admin=True,
        )
    )
    db.commit()
    res = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "password123"}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def offer(db):
    """A centre that offers one test at 500.00."""
    centre = DiagnosticCentre(name="City Lab", location="Delhi")
    test = DiagnosticTest(name="CBC")
    db.add_all([centre, test])
    db.flush()
    db.add(CentreTest(centre_id=centre.id, test_id=test.id, price=Decimal("500.00")))
    db.commit()
    return {"centre_id": centre.id, "test_id": test.id, "price": "500.00"}
