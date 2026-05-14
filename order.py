"""
app/services/order.py
─────────────────────────────────────────────────────────────────────────────
Business logic for orders.

FIX: place_order now clears the user's cart after successful order placement.
FIX: place_order uses SELECT FOR UPDATE to prevent race conditions on stock.
─────────────────────────────────────────────────────────────────────────────
"""

import math
from decimal import Decimal

from fastapi import HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy.orm import Session, joinedload
from loguru import logger

from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.order import (
    OrderCreate, OrderStatusUpdate,
    OrderResponse, OrderListResponse, OrderItemResponse,
)
from app.services.cache import cache_delete, cache_delete_pattern

# ─── Valid status transitions ─────────────────────────────────────────────────
VALID_TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
    OrderStatus.PENDING:    [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
    OrderStatus.CONFIRMED:  [OrderStatus.SHIPPED,   OrderStatus.CANCELLED],
    OrderStatus.SHIPPED:    [OrderStatus.DELIVERED],
    OrderStatus.DELIVERED:  [],
    OrderStatus.CANCELLED:  [],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_order_response(order: Order) -> OrderResponse:
    """Convert an ORM Order (with loaded items) to a response schema."""
    items = [
        OrderItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_name=item.product.name if item.product else "",
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item.subtotal,
        )
        for item in order.items
    ]
    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        status=order.status,
        total_amount=order.total_amount,
        shipping_address=order.shipping_address,
        items=items,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _load_order(order_id: int, db: Session) -> Order:
    """Load an order with all relationships eagerly."""
    order = (
        db.query(Order)
        .options(
            joinedload(Order.items).joinedload(OrderItem.product),
            joinedload(Order.user),
        )
        .filter(Order.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order id={order_id} not found.",
        )
    return order


# ─── Service functions ────────────────────────────────────────────────────────

def place_order(payload: OrderCreate, current_user: User, db: Session) -> OrderResponse:
    """
    Place a new order for the authenticated user.

    Steps:
      1. Validate every product exists and is in stock (uses row-level lock).
      2. Deduct stock from each product atomically.
      3. Create the Order and OrderItem rows.
      4. Compute and store the total_amount.
      5. Clear the user's Redis cart on success.
    """
    order = Order(
        user_id=current_user.id,
        status=OrderStatus.PENDING,
        shipping_address=payload.shipping_address,
        total_amount=Decimal("0.00"),
    )
    db.add(order)
    db.flush()

    total = Decimal("0.00")

    for line in payload.items:
        # with_for_update() prevents simultaneous over-selling
        product = (
            db.query(Product)
            .filter(
                Product.id == line.product_id,
                Product.is_active == True,  # noqa: E712
            )
            .with_for_update()
            .first()
        )

        if not product:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product id={line.product_id} not found or inactive.",
            )
        if product.stock_quantity < line.quantity:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient stock for '{product.name}'. "
                    f"Available: {product.stock_quantity}, requested: {line.quantity}."
                ),
            )

        product.stock_quantity -= line.quantity

        unit_price = product.price
        db.add(OrderItem(
            order_id=order.id,
            product_id=line.product_id,
            quantity=line.quantity,
            unit_price=unit_price,
        ))
        total += unit_price * line.quantity

    order.total_amount = total
    db.commit()

    # Narrower cache invalidation: only kill list caches (which paginate
    # over stock) and the per-product entries we actually touched. The
    # categories cache is unaffected by stock changes.
    cache_delete_pattern("products:list:*")
    for line in payload.items:
        cache_delete(f"products:{line.product_id}")
    cache_delete_pattern(f"orders:user:{current_user.id}:*")

    # Clear the user's cart after a successful order. Redis failure here
    # must not roll back the order — the order is already committed.
    try:
        from app.services.cart import clear_cart
        clear_cart(current_user.id)
    except RedisError as exc:
        logger.warning("Cart clear failed after order {}: {}", order.id, exc)

    order = _load_order(order.id, db)
    logger.info(
        "Order placed: id={} user_id={} total={}",
        order.id, current_user.id, total,
    )
    return _build_order_response(order)


def cancel_order(order_id: int, current_user: User, db: Session) -> OrderResponse:
    """
    Cancel an order and restore product stock.

    Rules:
      - Customers can only cancel their own PENDING orders.
      - Admins can cancel any PENDING or CONFIRMED order.
    """
    order = _load_order(order_id, db)

    if current_user.role == UserRole.CUSTOMER and order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only cancel your own orders.")

    if OrderStatus.CANCELLED not in VALID_TRANSITIONS.get(order.status, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel an order with status '{order.status}'.",
        )

    for item in order.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            product.stock_quantity += item.quantity

    order.status = OrderStatus.CANCELLED
    db.commit()

    # Narrower invalidation: list caches + per-product entries we restored.
    cache_delete_pattern("products:list:*")
    for item in order.items:
        cache_delete(f"products:{item.product_id}")
    cache_delete_pattern(f"orders:user:{order.user_id}:*")
    logger.info("Order cancelled: id={} by user_id={}", order_id, current_user.id)

    order = _load_order(order_id, db)
    return _build_order_response(order)


def update_order_status(
    order_id: int, payload: OrderStatusUpdate, db: Session
) -> OrderResponse:
    """Admin-only: move an order to a new status, enforcing valid transitions."""
    order = _load_order(order_id, db)
    allowed = VALID_TRANSITIONS.get(order.status, [])

    if payload.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot transition from '{order.status}' to '{payload.status}'. "
                f"Allowed transitions: {[s.value for s in allowed]}."
            ),
        )

    order.status = payload.status
    db.commit()

    cache_delete_pattern(f"orders:user:{order.user_id}:*")
    logger.info("Order status updated: id={} → {}", order_id, payload.status)

    order = _load_order(order_id, db)
    return _build_order_response(order)


def get_order_by_id(
    order_id: int, current_user: User, db: Session
) -> OrderResponse:
    """
    Retrieve a single order.
    Customers can only retrieve their own; admins can retrieve any.
    """
    order = _load_order(order_id, db)
    if current_user.role == UserRole.CUSTOMER and order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return _build_order_response(order)


def list_orders(
    current_user: User,
    db: Session,
    page: int = 1,
    page_size: int = 10,
) -> OrderListResponse:
    """
    Return paginated orders.
    Admins see all orders; customers see only their own.
    """
    query = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.product)
    )

    if current_user.role == UserRole.CUSTOMER:
        query = query.filter(Order.user_id == current_user.id)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total else 1
    orders = (
        query
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return OrderListResponse(
        items=[_build_order_response(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
