"""
app/core/dependencies.py
─────────────────────────────────────────────────────────────────────────────
Reusable FastAPI dependencies.

FIX: unauthenticated requests now return 401 (not 403).
     HTTPBearer auto_error=False lets us return a proper 401 message.

Provides:
  - get_current_user()        : validates Bearer token → returns User ORM obj
  - get_current_active_user() : also checks is_active flag
  - require_admin()           : admin role guard
  - require_customer()        : customer role guard
─────────────────────────────────────────────────────────────────────────────
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session
from loguru import logger

from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User, UserRole

# auto_error=False so we can return a custom 401 instead of FastAPI's default 403
bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials. Please log in again.",
    headers={"WWW-Authenticate": "Bearer"},
)


# ─── Token → User ────────────────────────────────────────────────────────────
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Decode the JWT from the Authorization header and return the matching User.

    FIXED: Returns 401 (not 403) when no token is supplied.
    """
    if credentials is None:
        raise _UNAUTHORIZED

    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            logger.warning("Token payload missing 'sub' claim")
            raise _UNAUTHORIZED
    except JWTError as exc:
        logger.warning("JWT validation failed: {}", exc)
        raise _UNAUTHORIZED

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        logger.warning("Token references non-existent user id={}", user_id)
        raise _UNAUTHORIZED

    return user


# ─── Active user guard ───────────────────────────────────────────────────────
def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensures the authenticated user account is not deactivated."""
    if not current_user.is_active:
        logger.warning("Inactive user id={} attempted access", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact support.",
        )
    return current_user


# ─── Role guards ─────────────────────────────────────────────────────────────
def require_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Restricts the endpoint to admin users only."""
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "User id={} (role={}) attempted admin-only action",
            current_user.id,
            current_user.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this operation.",
        )
    return current_user


def require_customer(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Restricts the endpoint to customer users only."""
    if current_user.role != UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer access required for this operation.",
        )
    return current_user
