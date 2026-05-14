"""
app/core/logging.py
─────────────────────────────────────────────────────────────────────────────
Centralised logging configuration using loguru.

Features:
  - Console output with colour-coded log levels
  - JSON-structured file output (machine-readable for dashboards)
  - Separate error log file
  - Rotating log files to prevent unbounded disk growth
  - In-memory log store for the monitoring dashboard endpoint

Log levels used across the project:
  DEBUG    – detailed diagnostic information (dev only)
  INFO     – normal operation events (requests, logins, CRUD)
  WARNING  – unexpected but recoverable situations
  ERROR    – failures that need attention
  CRITICAL – severe failures (DB down, service unavailable)
─────────────────────────────────────────────────────────────────────────────
Member responsibility: Member 4 (testing-dashboard branch)
"""

import sys
import json
from collections import deque
from datetime import datetime
from pathlib import Path
from loguru import logger

from app.config import settings

# ─── In-memory log buffer for the dashboard ──────────────────────────────────
# Stores the last 500 log entries as dicts; thread-safe for reads
LOG_BUFFER: deque = deque(maxlen=500)

# ─── Request metrics store ───────────────────────────────────────────────────
# Accumulated per-endpoint stats used by the dashboard
REQUEST_METRICS: dict = {}


# ─── Log directory ───────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def _buffer_sink(message):
    """
    Custom loguru sink that appends structured records to LOG_BUFFER.
    Called for every log message regardless of level.
    """
    record = message.record
    LOG_BUFFER.append({
        "time": record["time"].strftime("%Y-%m-%d %H:%M:%S"),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
    })


def setup_logging() -> None:
    """
    Configure loguru with all required sinks.
    Called once during application startup (app/main.py lifespan).
    """
    # Remove the default loguru handler
    logger.remove()

    # ── Sink 1: Console (human-readable, coloured) ───────────────────────────
    log_level = "DEBUG" if settings.debug else "INFO"
    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # ── Sink 2: JSON file (structured, for dashboards / log shippers) ────────
    logger.add(
        LOG_DIR / "app.json",
        level="DEBUG",
        format="{message}",          # We serialise to JSON below
        serialize=True,              # loguru built-in JSON serialisation
        rotation="10 MB",            # Rotate when file hits 10 MB
        retention="14 days",         # Keep last 14 days of rotated files
        compression="zip",           # Compress rotated files
        enqueue=True,                # Non-blocking writes
    )

    # ── Sink 3: Error-only file ───────────────────────────────────────────────
    logger.add(
        LOG_DIR / "errors.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function}:{line} | {message}",
        rotation="5 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,
    )

    # ── Sink 4: In-memory buffer (powers the /dashboard endpoint) ────────────
    logger.add(_buffer_sink, level="DEBUG", format="{message}")

    logger.info("Logging system initialised (level={})", log_level)


def record_request_metric(
    method: str,
    endpoint: str,
    status_code: int,
    response_time_ms: float,
) -> None:
    """
    Update the in-memory metrics store with stats for a completed request.
    Called by the request-logging middleware in main.py.

    Args:
        method:           HTTP verb (GET, POST, …)
        endpoint:         URL path (e.g. /api/v1/products)
        status_code:      HTTP response status code
        response_time_ms: Round-trip time in milliseconds
    """
    key = f"{method} {endpoint}"

    if key not in REQUEST_METRICS:
        REQUEST_METRICS[key] = {
            "method": method,
            "endpoint": endpoint,
            "total_requests": 0,
            "total_errors": 0,
            "total_response_time_ms": 0.0,
            "avg_response_time_ms": 0.0,
            "last_status_code": status_code,
        }

    entry = REQUEST_METRICS[key]
    entry["total_requests"] += 1
    entry["total_response_time_ms"] += response_time_ms
    entry["avg_response_time_ms"] = (
        entry["total_response_time_ms"] / entry["total_requests"]
    )
    entry["last_status_code"] = status_code

    if status_code >= 400:
        entry["total_errors"] += 1