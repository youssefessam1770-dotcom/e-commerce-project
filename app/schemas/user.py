"""
app/schemas/user.py
─────────────────────────────────────────────────────────────────────────────
Pydantic v2 schemas for User request/response validation.

Schema naming convention:
  UserCreate   – body of POST /auth/register
  UserLogin    – body of POST /auth/login
  UserUpdate   – body of PUT  /users/{id}  (partial update)
  UserResponse – safe public representation (no password)
  Token        – JWT response body
  TokenData    – claims extracted from a decoded JWT
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 1 (auth branch)
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole


# ─── Shared validators ────────────────────────────────────────────────────────
def _validate_password(v: str) -> str:
    """
    Enforce a minimum password policy:
      - At least 8 characters
      - At least one uppercase letter
      - At least one digit
    """
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not any(c.isupper() for c in v):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one digit.")
    return v


# ─── Request schemas ──────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    """Schema for registering a new user account."""

    username: Annotated[str, Field(min_length=3, max_length=50, examples=["john_doe"])]
    email: EmailStr
    password: Annotated[str, Field(min_length=8, examples=["Secret@123"])]
    full_name: Annotated[str | None, Field(max_length=100, default=None)]

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        return _validate_password(v)


class UserLogin(BaseModel):
    """Schema for the login endpoint."""

    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """
    Schema for updating user profile.
    All fields are optional; only provided fields are updated.
    """

    full_name: Annotated[str | None, Field(max_length=100, default=None)]
    email: EmailStr | None = None
    password: Annotated[str | None, Field(min_length=8, default=None)] = None
    is_active: bool | None = None                  # Admin only

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_password(v)
        return v


# ─── Response schemas ─────────────────────────────────────────────────────────
class UserResponse(BaseModel):
    """Public-safe user representation returned from all user endpoints."""

    id: int
    username: str
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}   # Allow ORM → Pydantic conversion


# ─── Auth schemas ─────────────────────────────────────────────────────────────
class Token(BaseModel):
    """Returned from POST /auth/login on success."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    """Claims extracted from a decoded JWT (used internally by dependencies)."""

    user_id: int
    role: UserRole