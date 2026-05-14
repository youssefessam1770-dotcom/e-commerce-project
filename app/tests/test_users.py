"""
app/tests/test_users.py
─────────────────────────────────────────────────────────────────────────────
Tests for user management endpoints:
  - Admin-only list/get users
  - Self-update vs admin update
  - Deactivate user (admin only)
─────────────────────────────────────────────────────────────────────────────
"""

import pytest

USERS_URL = "/api/v1/users"
REGISTER_URL = "/api/v1/auth/register"


class TestUserManagement:
    def test_admin_can_list_users(self, client, admin_headers):
        resp = client.get(USERS_URL, headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_customer_cannot_list_users(self, client, customer_headers):
        resp = client.get(USERS_URL, headers=customer_headers)
        assert resp.status_code == 403

    def test_unauthenticated_cannot_list_users(self, client):
        resp = client.get(USERS_URL)
        assert resp.status_code == 401

    def test_admin_can_get_user_by_id(self, client, admin_headers):
        # Register a fresh user to look up
        client.post(REGISTER_URL, json={
            "username": "lookupuser",
            "email": "lookup@test.com",
            "password": "Lookup@123",
        })
        users = client.get(USERS_URL, headers=admin_headers).json()
        user_id = next(u["id"] for u in users if u["email"] == "lookup@test.com")
        resp = client.get(f"{USERS_URL}/{user_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "lookup@test.com"

    def test_get_nonexistent_user(self, client, admin_headers):
        resp = client.get(f"{USERS_URL}/99999", headers=admin_headers)
        assert resp.status_code == 404

    def test_customer_can_update_own_profile(self, client, customer_headers):
        # Get own ID via /auth/me
        me = client.get("/api/v1/auth/me", headers=customer_headers).json()
        resp = client.put(
            f"{USERS_URL}/{me['id']}",
            json={"full_name": "Updated Name"},
            headers=customer_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"

    def test_customer_cannot_update_other_user(self, client, customer_headers, admin_headers):
        # Get admin's ID
        admin_me = client.get("/api/v1/auth/me", headers=admin_headers).json()
        resp = client.put(
            f"{USERS_URL}/{admin_me['id']}",
            json={"full_name": "Hacked"},
            headers=customer_headers,
        )
        assert resp.status_code == 403

    def test_admin_can_deactivate_user(self, client, admin_headers):
        client.post(REGISTER_URL, json={
            "username": "deactivateme",
            "email": "deactivate@test.com",
            "password": "Deact@123",
        })
        users = client.get(USERS_URL, headers=admin_headers).json()
        user_id = next(u["id"] for u in users if u["email"] == "deactivate@test.com")
        resp = client.delete(f"{USERS_URL}/{user_id}", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_cannot_deactivate_self(self, client, admin_headers):
        me = client.get("/api/v1/auth/me", headers=admin_headers).json()
        resp = client.delete(f"{USERS_URL}/{me['id']}", headers=admin_headers)
        assert resp.status_code == 400

    def test_hashed_password_not_in_response(self, client, admin_headers):
        users = client.get(USERS_URL, headers=admin_headers).json()
        for user in users:
            assert "hashed_password" not in user
            assert "password" not in user
