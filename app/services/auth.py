"""
app/services/auth.py
─────────────────────────────────────────────────────────────────────────────
Business logic for authentication: register, login, seed first admin.
Routes stay thin — all DB logic lives here.
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 1 (auth branch)
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from loguru import logger

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserLogin, Token, UserResponse


def register_user(payload: UserCreate, db: Session) -> UserResponse:
    """
    Create a new customer account.

    Raises:
        409 if the email or username is already taken.
    """
    # Check uniqueness
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken.",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.CUSTOMER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("New user registered: id={} email={}", user.id, user.email)
    return UserResponse.model_validate(user)


def login_user(payload: UserLogin, db: Session) -> Token:
    """
    Authenticate a user and return a JWT access token.

    Raises:
        401 if credentials are invalid or account is deactivated.
    """
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        logger.warning("Failed login attempt for email={}", payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning("Login attempt by deactivated user id={}", user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact support.",
        )

    token = create_access_token(
        subject=user.id,
        extra_claims={"role": user.role.value},
    )

    logger.info("User logged in: id={} role={}", user.id, user.role)
    return Token(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


def seed_admin_user(db: Session) -> None:
    """
    Create the first admin account on application startup if it doesn't exist.
    Reads credentials from environment variables via settings.
    """
    from app.config import settings

    existing = db.query(User).filter(User.role == UserRole.ADMIN).first()
    if existing:
        return  # Admin already exists, nothing to do

    admin = User(
        username=settings.first_admin_username,
        email=settings.first_admin_email,
        hashed_password=hash_password(settings.first_admin_password),
        full_name="System Administrator",
        role=UserRole.ADMIN,
    )
    db.add(admin)
    db.commit()
    logger.info(
        "Seeded first admin user: email={}", settings.first_admin_email
    )