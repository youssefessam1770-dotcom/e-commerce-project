"""
app/routes/users.py
─────────────────────────────────────────────────────────────────────────────
User management endpoints (admin only except self-update):
  GET    /api/v1/users          → list all users           [admin]
  GET    /api/v1/users/{id}     → get user by id           [admin]
  PUT    /api/v1/users/{id}     → update user              [admin or self]
  DELETE /api/v1/users/{id}     → deactivate user          [admin]
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 1 (auth branch)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from loguru import logger

from app.core.dependencies import get_current_active_user, require_admin
from app.core.security import hash_password
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List all users [Admin only]",
)
def list_users(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Returns all registered users. Admin access required."""
    return db.query(User).all()


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID [Admin only]",
)
def get_user(
    user_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Fetch a specific user profile by ID. Admin access required."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update a user [Admin or self]",
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Update user fields. Rules:
    - Customers can only update their own profile.
    - Only admins can change `is_active`.
    """
    from app.models.user import UserRole

    # Customers can only edit themselves
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own profile.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    update_data = payload.model_dump(exclude_none=True)

    # Non-admins cannot change is_active
    if current_user.role != UserRole.ADMIN:
        update_data.pop("is_active", None)

    # Hash the new password if provided
    if "password" in update_data:
        update_data["hashed_password"] = hash_password(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    logger.info("User updated: id={} by user_id={}", user_id, current_user.id)
    return user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Deactivate a user account [Admin only]",
)
def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Soft-delete: sets is_active=False. Admin access required."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate yourself.")

    user.is_active = False
    db.commit()
    logger.info("User deactivated: id={} by admin id={}", user_id, current_user.id)
    return {"detail": f"User id={user_id} deactivated successfully."}