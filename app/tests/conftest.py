"""
app/tests/conftest.py
─────────────────────────────────────────────────────────────────────────────
pytest fixtures shared across all test modules.

Setup:
  - Uses an in-memory SQLite database (no PostgreSQL required for tests)
  - Mocks the Redis cache so tests don't need a running Redis instance
  - Provides authenticated client fixtures for both roles (admin / customer)
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 4 (testing-dashboard branch)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch, MagicMock

from app.database import Base, get_db
from app.main import app

# ─── In-memory SQLite engine for tests ───────────────────────────────────────
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """Create all tables once for the entire test session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db():
    """Provide a fresh DB session and roll back after each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """
    TestClient with:
      - DB dependency overridden to use the test SQLite session
      - Redis calls mocked out (cache always returns None = cache miss)
    """
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Mock all Redis cache functions so tests never need a Redis server
    with patch("app.services.cache.cache_get", return_value=None), \
         patch("app.services.cache.cache_set", return_value=True), \
         patch("app.services.cache.cache_delete", return_value=True), \
         patch("app.services.cache.cache_delete_pattern", return_value=0):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


# ─── Helper: register + login to get a token ─────────────────────────────────

def _register_and_login(client: TestClient, email: str, username: str, password: str = "Test@1234") -> str:
    """Register a user and return a Bearer token string."""
    client.post("/api/v1/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
        "full_name": "Test User",
    })
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture()
def customer_token(client) -> str:
    """JWT token for a freshly registered customer."""
    return _register_and_login(client, "customer@test.com", "testcustomer")


@pytest.fixture()
def customer_headers(customer_token) -> dict:
    return {"Authorization": f"Bearer {customer_token}"}


@pytest.fixture()
def admin_headers(client) -> dict:
    """
    JWT token for the seeded admin user.
    The admin is auto-created during app startup (lifespan).
    """
    from app.config import settings
    resp = client.post("/api/v1/auth/login", json={
        "email": settings.first_admin_email,
        "password": settings.first_admin_password,
    })
    token = resp.json().get("access_token", "")
    return {"Authorization": f"Bearer {token}"}