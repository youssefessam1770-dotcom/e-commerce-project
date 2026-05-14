"""
app/core/security.py
─────────────────────────────────────────────────────────────────────────────
Cryptographic helpers:
  - Password hashing  (bcrypt via passlib)
  - JWT creation & verification  (python-jose)
  - Token type guard (prevents refresh tokens used as access tokens)
─────────────────────────────────────────────────────────────────────────────
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ─── Password hashing ────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ─── JWT Token management ────────────────────────────────────────────────────
def create_access_token(
    subject: str | int,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject:      The unique identifier to embed (typically user ID).
        extra_claims: Optional additional claims (e.g. {"role": "admin"}).

    Returns:
        A signed JWT string ready to be returned to the client.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )

    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT access token.

    Raises:
        JWTError: If the token is invalid, expired, or tampered with.
    """
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.algorithm],
    )
    if payload.get("type") == "refresh":
        raise JWTError("Cannot use refresh token as access token.")
    return payload
