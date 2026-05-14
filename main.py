"""
app/main.py
─────────────────────────────────────────────────────────────────────────────
FastAPI application entry point.

IMPROVEMENTS:
  - Validation error handler now returns 422 with clear field errors
  - Unhandled exception handler logs full traceback
  - CORS origins restricted (not wildcard) when not in debug mode
─────────────────────────────────────────────────────────────────────────────
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings
from app.core.logging import record_request_metric, setup_logging
from app.database import SessionLocal, engine, Base

# Import all models so SQLAlchemy registers them with Base.metadata
from app.models.user import User        # noqa: F401
from app.models.product import Category, Product  # noqa: F401
from app.models.order import Order, OrderItem     # noqa: F401

# Routes
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.orders import router as orders_router
from app.routes.cart import router as cart_router
from app.routes.products import categories_router, products_router
from app.routes.users import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting {} v{}", settings.app_name, settings.app_version)

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified / created")

    db = SessionLocal()
    try:
        from app.services.auth import seed_admin_user
        seed_admin_user(db)
    finally:
        db.close()

    logger.info("Application startup complete - ready to serve requests")
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="DSC 306 E-Commerce Backend API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — restrict origins in production
_cors_origins = ["*"] if settings.debug else ["http://localhost:3000", "http://localhost:5500"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request logging middleware ───────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    logger.info("-> {} {}", request.method, request.url.path)
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "<- {} {} {} {:.1f}ms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    record_request_metric(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
        response_time_ms=duration_ms,
    )
    return response


# ─── Exception handlers ───────────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured 422 responses with field-level error details."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": " → ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })
    logger.debug("Validation error on {} {}: {}", request.method, request.url.path, errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation failed", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception on {} {}: {}",
        request.method, request.url.path, exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal error occurred."},
    )


# ─── Routers ──────────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"
app.include_router(auth_router,       prefix=API_PREFIX)
app.include_router(users_router,      prefix=API_PREFIX)
app.include_router(categories_router, prefix=API_PREFIX)
app.include_router(products_router,   prefix=API_PREFIX)
app.include_router(orders_router,     prefix=API_PREFIX)
app.include_router(cart_router,       prefix=API_PREFIX)
app.include_router(dashboard_router,  prefix=API_PREFIX)


@app.get("/", tags=["Root"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "dashboard": "/api/v1/dashboard/",
    }
