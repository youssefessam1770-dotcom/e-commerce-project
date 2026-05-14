"""
app/database.py
─────────────────────────────────────────────────────────────────────────────
SQLAlchemy async-compatible setup with PostgreSQL.
Provides:
  - engine        : SQLAlchemy Engine
  - SessionLocal  : session factory (used as a dependency in routes)
  - Base          : declarative base all models inherit from
  - get_db()      : FastAPI dependency that yields a DB session and
                    guarantees it is closed after each request
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 1 (auth branch)
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

from app.config import settings


# ─── Engine ──────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    # Keep a pool of up to 10 connections; overflow allows 20 extra under load
    pool_size=10,
    max_overflow=20,
    # Recycle connections every 30 minutes to avoid stale connection issues
    pool_recycle=1800,
    # Log all SQL statements when DEBUG=True
    echo=settings.debug,
)


# ─── Session Factory ─────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,   # We commit explicitly so we control transactions
    autoflush=False,    # Flush only when we call session.flush() or commit()
    expire_on_commit=False,  # Keep objects usable after commit
)


# ─── Declarative Base ────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """
    All ORM models inherit from this base.
    Provides __tablename__ convention and shared metadata.
    """
    pass


# ─── Dependency ──────────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session per request.

    Usage in a route:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...

    The session is always closed in the finally block, even if an
    exception is raised inside the route handler.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()