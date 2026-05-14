"""
app/services/cart.py
─────────────────────────────────────────────────────────────────────────────
Shopping cart business logic — stored in Redis per user.

Cart key pattern: cart:{user_id}
Cart value:       JSON dict { product_id: quantity, ... }
TTL:              24 hours (auto-expires if user abandons cart)
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 3 (orders-cart branch)
"""

import json
from fastapi import HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy.orm import Session
from loguru import logger

from app.models.product import Product
from app.services.cache import get_redis_client


CART_TTL = 60 * 60 * 24  # 24 hours


def _cart_key(user_id: int) -> str:
    return f"cart:{user_id}"


def _load_cart(user_id: int) -> dict:
    """Load raw cart dict {product_id_str: quantity} from Redis."""
    try:
        client = get_redis_client()
        raw = client.get(_cart_key(user_id))
        return json.loads(raw) if raw else {}
    except RedisError as exc:
        logger.warning("Failed to read cart for user {}: {}", user_id, exc)
        return {}
    except (ValueError, TypeError) as exc:
        logger.warning("Corrupt cart payload for user {}: {}", user_id, exc)
        return {}


def _save_cart(user_id: int, cart: dict) -> None:
    """Persist cart back to Redis with TTL refresh."""
    try:
        client = get_redis_client()
        client.setex(_cart_key(user_id), CART_TTL, json.dumps(cart))
    except RedisError as exc:
        logger.warning("Failed to save cart for user {}: {}", user_id, exc)


def _build_response(user_id: int, cart: dict, db: Session) -> dict:
    """Enrich cart with product details and compute totals."""
    items = []
    total = 0.0
    for pid_str, qty in cart.items():
        product = db.query(Product).filter(
            Product.id == int(pid_str),
            Product.is_active == True,  # noqa: E712
        ).first()
        if not product:
            continue  # Product removed/deactivated — skip silently
        subtotal = float(product.price) * qty
        total += subtotal
        items.append({
            "product_id": product.id,
            "product_name": product.name,
            "unit_price": float(product.price),
            "quantity": qty,
            "subtotal": round(subtotal, 2),
        })
    return {"user_id": user_id, "items": items, "total": round(total, 2)}


def get_cart(user_id: int, db: Session) -> dict:
    """Return the current user's cart."""
    cart = _load_cart(user_id)
    return _build_response(user_id, cart, db)


def add_to_cart(user_id: int, product_id: int, quantity: int, db: Session) -> dict:
    """
    Add or update a product in the cart.
    Validates product exists and stock is sufficient.
    """
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.is_active == True,  # noqa: E712
    ).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product id={product_id} not found or inactive.",
        )
    if product.stock_quantity < quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {product.stock_quantity} units available for '{product.name}'.",
        )

    cart = _load_cart(user_id)
    cart[str(product_id)] = quantity
    _save_cart(user_id, cart)
    logger.info("Cart updated: user={} product={} qty={}", user_id, product_id, quantity)
    return _build_response(user_id, cart, db)


def remove_from_cart(user_id: int, product_id: int, db: Session) -> dict:
    """Remove a single product from the cart."""
    cart = _load_cart(user_id)
    if str(product_id) not in cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product id={product_id} not in cart.",
        )
    del cart[str(product_id)]
    _save_cart(user_id, cart)
    logger.info("Cart item removed: user={} product={}", user_id, product_id)
    return _build_response(user_id, cart, db)


def clear_cart(user_id: int) -> None:
    """Empty the cart completely (called after order is placed)."""
    try:
        client = get_redis_client()
        client.delete(_cart_key(user_id))
        logger.info("Cart cleared: user={}", user_id)
    except RedisError as exc:
        logger.warning("Failed to clear cart for user {}: {}", user_id, exc)
