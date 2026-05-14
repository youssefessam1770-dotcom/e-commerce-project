"""
app/tests/test_auth.py
─────────────────────────────────────────────────────────────────────────────
Tests for authentication endpoints:
  - User registration (happy path + validation + duplicates)
  - User login (success + wrong password + inactive user)
  - /auth/me (authenticated route)
  - JWT token validation
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 4 (testing-dashboard branch)
"""

import pytest


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"

VALID_USER = {
    "username": "john_doe",
    "email": "john@example.com",
    "password": "Secret@123",
    "full_name": "John Doe",
}


class TestRegister:
    def test_register_success(self, client):
        resp = client.post(REGISTER_URL, json=VALID_USER)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == VALID_USER["email"]
        assert data["role"] == "customer"
        assert "hashed_password" not in data         # Never leak hash

    def test_register_duplicate_email(self, client):
        client.post(REGISTER_URL, json=VALID_USER)
        resp = client.post(REGISTER_URL, json=VALID_USER)
        assert resp.status_code == 409

    def test_register_duplicate_username(self, client):
        client.post(REGISTER_URL, json=VALID_USER)
        resp = client.post(REGISTER_URL, json={**VALID_USER, "email": "other@example.com"})
        assert resp.status_code == 409

    def test_register_weak_password_no_uppercase(self, client):
        resp = client.post(REGISTER_URL, json={**VALID_USER, "email": "x@x.com", "password": "alllower1"})
        assert resp.status_code == 422

    def test_register_weak_password_no_digit(self, client):
        resp = client.post(REGISTER_URL, json={**VALID_USER, "email": "x@x.com", "password": "NoDigitHere"})
        assert resp.status_code == 422

    def test_register_short_password(self, client):
        resp = client.post(REGISTER_URL, json={**VALID_USER, "email": "x@x.com", "password": "Ab1"})
        assert resp.status_code == 422

    def test_register_invalid_email(self, client):
        resp = client.post(REGISTER_URL, json={**VALID_USER, "email": "not-an-email"})
        assert resp.status_code == 422

    def test_register_missing_username(self, client):
        payload = {k: v for k, v in VALID_USER.items() if k != "username"}
        resp = client.post(REGISTER_URL, json=payload)
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client):
        client.post(REGISTER_URL, json=VALID_USER)
        resp = client.post(LOGIN_URL, json={"email": VALID_USER["email"], "password": VALID_USER["password"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == VALID_USER["email"]

    def test_login_wrong_password(self, client):
        client.post(REGISTER_URL, json=VALID_USER)
        resp = client.post(LOGIN_URL, json={"email": VALID_USER["email"], "password": "WrongPass1"})
        assert resp.status_code == 401

    def test_login_nonexistent_email(self, client):
        resp = client.post(LOGIN_URL, json={"email": "ghost@example.com", "password": "Whatever1"})
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post(LOGIN_URL, json={"email": VALID_USER["email"]})
        assert resp.status_code == 422


class TestMe:
    def test_me_authenticated(self, client, customer_headers):
        resp = client.get(ME_URL, headers=customer_headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "customer"

    def test_me_no_token(self, client):
        resp = client.get(ME_URL)
        assert resp.status_code == 403

    def test_me_invalid_token(self, client):
        resp = client.get(ME_URL, headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401