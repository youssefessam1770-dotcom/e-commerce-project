"""
app/tests/test_orders.py
─────────────────────────────────────────────────────────────────────────────
Tests for the order lifecycle:
  - Place order (success, out-of-stock, invalid product)
  - Get/list orders (ownership rules)
  - Cancel order (valid states, stock restoration)
  - Admin status transitions (valid and invalid)
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 4 (testing-dashboard branch)
"""

import pytest

CATEGORIES_URL = "/api/v1/categories"
PRODUCTS_URL = "/api/v1/products"
ORDERS_URL = "/api/v1/orders"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def create_product(client, admin_headers, stock=10, price=50.0):
    cat = client.post(CATEGORIES_URL, json={"name": "TestCat"}, headers=admin_headers).json()
    return client.post(PRODUCTS_URL, json={
        "name": "Test Product",
        "price": price,
        "stock_quantity": stock,
        "category_id": cat["id"],
    }, headers=admin_headers).json()


def place_order(client, headers, product_id, quantity=1, address="123 Test St"):
    return client.post(ORDERS_URL, json={
        "items": [{"product_id": product_id, "quantity": quantity}],
        "shipping_address": address,
    }, headers=headers)


# ──────────────────────────────────────────────────────────────────────────────
# PLACE ORDER
# ──────────────────────────────────────────────────────────────────────────────

class TestPlaceOrder:
    def test_place_order_success(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers, stock=10)
        resp = place_order(client, customer_headers, product["id"], quantity=2)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert len(data["items"]) == 1
        assert data["items"][0]["quantity"] == 2
        assert float(data["total_amount"]) == 100.0  # 50 * 2

    def test_place_order_reduces_stock(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers, stock=10)
        place_order(client, customer_headers, product["id"], quantity=3)
        # Check updated stock
        updated = client.get(f"{PRODUCTS_URL}/{product['id']}").json()
        assert updated["stock_quantity"] == 7

    def test_place_order_insufficient_stock(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers, stock=2)
        resp = place_order(client, customer_headers, product["id"], quantity=5)
        assert resp.status_code == 400

    def test_place_order_product_not_found(self, client, customer_headers):
        resp = place_order(client, customer_headers, product_id=99999)
        assert resp.status_code == 404

    def test_place_order_unauthenticated(self, client, admin_headers):
        product = create_product(client, admin_headers)
        resp = client.post(ORDERS_URL, json={
            "items": [{"product_id": product["id"], "quantity": 1}]
        })
        assert resp.status_code == 401

    def test_place_order_zero_quantity(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers)
        resp = place_order(client, customer_headers, product["id"], quantity=0)
        assert resp.status_code == 422

    def test_place_order_empty_items(self, client, customer_headers):
        resp = client.post(ORDERS_URL, json={"items": []}, headers=customer_headers)
        assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# GET / LIST ORDERS
# ──────────────────────────────────────────────────────────────────────────────

class TestGetOrders:
    def test_customer_can_get_own_order(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers)
        order = place_order(client, customer_headers, product["id"]).json()
        resp = client.get(f"{ORDERS_URL}/{order['id']}", headers=customer_headers)
        assert resp.status_code == 200

    def test_customer_cannot_get_other_order(self, client, admin_headers, customer_headers):
        # Admin places an order
        product = create_product(client, admin_headers)
        admin_resp = client.post("/api/v1/auth/login", json={
            "email": "admin@ecommerce.com",
            "password": "Admin@123456",
        })
        admin_order_headers = {"Authorization": f"Bearer {admin_resp.json().get('access_token', '')}"}
        order = place_order(client, admin_order_headers, product["id"]).json()

        # Customer tries to read it
        resp = client.get(f"{ORDERS_URL}/{order['id']}", headers=customer_headers)
        assert resp.status_code == 403

    def test_admin_can_list_all_orders(self, client, admin_headers, customer_headers):
        product = create_product(client, admin_headers)
        place_order(client, customer_headers, product["id"])
        resp = client.get(ORDERS_URL, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_list_orders_paginated(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers)
        for _ in range(3):
            place_order(client, customer_headers, product["id"])
        resp = client.get(f"{ORDERS_URL}?page=1&page_size=2", headers=customer_headers)
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 2


# ──────────────────────────────────────────────────────────────────────────────
# CANCEL ORDER
# ──────────────────────────────────────────────────────────────────────────────

class TestCancelOrder:
    def test_customer_cancels_own_pending_order(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers, stock=10)
        order = place_order(client, customer_headers, product["id"], quantity=2).json()
        resp = client.delete(f"{ORDERS_URL}/{order['id']}", headers=customer_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_restores_stock(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers, stock=10)
        order = place_order(client, customer_headers, product["id"], quantity=3).json()
        client.delete(f"{ORDERS_URL}/{order['id']}", headers=customer_headers)
        updated = client.get(f"{PRODUCTS_URL}/{product['id']}").json()
        assert updated["stock_quantity"] == 10  # Fully restored

    def test_cannot_cancel_delivered_order(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers, stock=10)
        order = place_order(client, customer_headers, product["id"]).json()

        # Admin moves through lifecycle to delivered
        for new_status in ["confirmed", "shipped", "delivered"]:
            client.put(
                f"{ORDERS_URL}/{order['id']}/status",
                json={"status": new_status},
                headers=admin_headers,
            )

        resp = client.delete(f"{ORDERS_URL}/{order['id']}", headers=customer_headers)
        assert resp.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# STATUS TRANSITIONS
# ──────────────────────────────────────────────────────────────────────────────

class TestOrderStatusTransitions:
    def _get_order(self, client, customer_headers, admin_headers):
        product = create_product(client, admin_headers, stock=20)
        return place_order(client, customer_headers, product["id"]).json()

    def test_valid_transition_pending_to_confirmed(self, client, customer_headers, admin_headers):
        order = self._get_order(client, customer_headers, admin_headers)
        resp = client.put(
            f"{ORDERS_URL}/{order['id']}/status",
            json={"status": "confirmed"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    def test_valid_transition_confirmed_to_shipped(self, client, customer_headers, admin_headers):
        order = self._get_order(client, customer_headers, admin_headers)
        client.put(f"{ORDERS_URL}/{order['id']}/status", json={"status": "confirmed"}, headers=admin_headers)
        resp = client.put(f"{ORDERS_URL}/{order['id']}/status", json={"status": "shipped"}, headers=admin_headers)
        assert resp.status_code == 200

    def test_invalid_transition_pending_to_delivered(self, client, customer_headers, admin_headers):
        order = self._get_order(client, customer_headers, admin_headers)
        resp = client.put(
            f"{ORDERS_URL}/{order['id']}/status",
            json={"status": "delivered"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_customer_cannot_update_status(self, client, customer_headers, admin_headers):
        order = self._get_order(client, customer_headers, admin_headers)
        resp = client.put(
            f"{ORDERS_URL}/{order['id']}/status",
            json={"status": "confirmed"},
            headers=customer_headers,
        )
        assert resp.status_code == 403