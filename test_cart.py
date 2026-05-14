"""
app/tests/test_cart.py
─────────────────────────────────────────────────────────────────────────────
Tests for the shopping cart endpoints (Redis-backed, per user).
─────────────────────────────────────────────────────────────────────────────
"""

import pytest
from unittest.mock import patch, MagicMock

CART_URL = "/api/v1/cart"
CATEGORIES_URL = "/api/v1/categories"
PRODUCTS_URL = "/api/v1/products"


def create_product(client, admin_headers, stock=20, price=25.0):
    cat = client.post(CATEGORIES_URL, json={"name": "CartCat"}, headers=admin_headers).json()
    return client.post(PRODUCTS_URL, json={
        "name": "Cart Product",
        "price": price,
        "stock_quantity": stock,
        "category_id": cat["id"],
    }, headers=admin_headers).json()


# ─── Helpers: mock Redis for cart ────────────────────────────────────────────
def make_redis_mock():
    """Return a Redis mock that behaves like a real in-memory store."""
    store = {}
    mock = MagicMock()
    mock.get.side_effect = lambda key: store.get(key)
    mock.setex.side_effect = lambda key, ttl, val: store.update({key: val})
    mock.delete.side_effect = lambda key: store.pop(key, None)
    return mock


class TestCart:
    def test_get_empty_cart(self, client, customer_headers):
        with patch("app.services.cart.get_redis_client") as mock_redis:
            mock_redis.return_value = make_redis_mock()
            resp = client.get(CART_URL, headers=customer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0.0

    def test_add_item_to_cart(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers)
        with patch("app.services.cart.get_redis_client") as mock_redis:
            mock_redis.return_value = make_redis_mock()
            resp = client.post(
                CART_URL,
                json={"product_id": product["id"], "quantity": 2},
                headers=customer_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["quantity"] == 2
        assert data["total"] == 50.0  # 25 * 2

    def test_add_item_exceeds_stock(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers, stock=3)
        with patch("app.services.cart.get_redis_client") as mock_redis:
            mock_redis.return_value = make_redis_mock()
            resp = client.post(
                CART_URL,
                json={"product_id": product["id"], "quantity": 999},
                headers=customer_headers,
            )
        assert resp.status_code == 400

    def test_add_nonexistent_product(self, client, customer_headers):
        with patch("app.services.cart.get_redis_client") as mock_redis:
            mock_redis.return_value = make_redis_mock()
            resp = client.post(
                CART_URL,
                json={"product_id": 99999, "quantity": 1},
                headers=customer_headers,
            )
        assert resp.status_code == 404

    def test_remove_item_from_cart(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers)
        redis_mock = make_redis_mock()
        with patch("app.services.cart.get_redis_client", return_value=redis_mock):
            client.post(
                CART_URL,
                json={"product_id": product["id"], "quantity": 1},
                headers=customer_headers,
            )
            resp = client.delete(
                f"{CART_URL}/{product['id']}",
                headers=customer_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_clear_cart(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers)
        redis_mock = make_redis_mock()
        with patch("app.services.cart.get_redis_client", return_value=redis_mock):
            client.post(
                CART_URL,
                json={"product_id": product["id"], "quantity": 1},
                headers=customer_headers,
            )
            resp = client.delete(CART_URL, headers=customer_headers)
        assert resp.status_code == 204

    def test_cart_requires_authentication(self, client):
        resp = client.get(CART_URL)
        assert resp.status_code == 401

    def test_zero_quantity_rejected(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers)
        with patch("app.services.cart.get_redis_client") as mock_redis:
            mock_redis.return_value = make_redis_mock()
            resp = client.post(
                CART_URL,
                json={"product_id": product["id"], "quantity": 0},
                headers=customer_headers,
            )
        assert resp.status_code == 422
