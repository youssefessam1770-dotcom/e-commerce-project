"""
app/routes/orders.py
─────────────────────────────────────────────────────────────────────────────
Order endpoints:
  GET    /api/v1/orders              → list orders (admin=all, customer=own)
  GET    /api/v1/orders/{id}         → single order (own or admin)
  POST   /api/v1/orders              → place a new order [customer/admin]
  PUT    /api/v1/orders/{id}/status  → update order status [admin]
  DELETE /api/v1/orders/{id}         → cancel order [customer=own, admin=any]
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 3 (orders-cart branch)
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.order import (
    OrderCreate, OrderListResponse, OrderResponse, OrderStatusUpdate,
)
import app.services.order as order_service
router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get(
    "",
    response_model=OrderListResponse,
    summary="List orders (admin=all, customer=own)",
)
def list_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    - **Admin**: returns all orders in the system (paginated)
    - **Customer**: returns only their own orders (paginated)
    """
    return order_service.list_orders(current_user, db, page, page_size)


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get a single order",
)
def get_order(
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve a specific order by ID.
    Customers can only retrieve their own orders.
    """
    return order_service.get_order_by_id(order_id, current_user, db)


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place a new order [Customer / Admin]",
)
def place_order(
    payload: OrderCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Place a new order. Validates:
    - All products exist and are active
    - Sufficient stock for each line item
    - Stock is atomically deducted on success
    """
    return order_service.place_order(payload, current_user, db)


@router.put(
    "/{order_id}/status",
    response_model=OrderResponse,
    summary="Update order status [Admin only]",
)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Move an order through its lifecycle.

    Valid transitions:
    - `pending` → `confirmed` or `cancelled`
    - `confirmed` → `shipped` or `cancelled`
    - `shipped` → `delivered`
    - `delivered` / `cancelled` → *(terminal, no further transitions)*
    """
    return order_service.update_order_status(order_id, payload, db)


@router.delete(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Cancel an order",
)
def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Cancel an order and restore product stock.
    - Customers can only cancel their own PENDING orders.
    - Admins can cancel any PENDING or CONFIRMED order.
    """
    return order_service.cancel_order(order_id, current_user, db)