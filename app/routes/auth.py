"""
app/routes/auth.py
─────────────────────────────────────────────────────────────────────────────
Authentication endpoints:
  POST /api/v1/auth/register  → create a new customer account
  POST /api/v1/auth/login     → authenticate and receive JWT
  GET  /api/v1/auth/me        → return the current user's profile
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 1 (auth branch)
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserResponse
from app.services.auth import login_user, register_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user with the CUSTOMER role.

    - **username**: 3–50 characters, must be unique
    - **email**: valid email address, must be unique
    - **password**: min 8 chars, at least one uppercase letter and one digit
    """
    return register_user(payload, db)


@router.post(
    "/login",
    response_model=Token,
    summary="Login and receive a JWT access token",
)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticate with email + password.

    Returns a **Bearer token** to include in the `Authorization` header
    of subsequent requests:
    ```
    Authorization: Bearer <access_token>
    ```
    """
    return login_user(payload, db)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the currently authenticated user's profile",
)
def get_me(current_user: User = Depends(get_current_active_user)):
    """
    Returns the profile of the user identified by the Bearer token.
    Requires a valid, non-expired JWT.
    """
    return current_user