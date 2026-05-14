# e-commerce-project

# 🛒 E-Commerce API — DSC 306 Group Project

Backend system built with **FastAPI**, **PostgreSQL**, **Redis**, and **JWT authentication**.

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-blue)](.github/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org)
[![Tests](https://img.shields.io/badge/tests-80%2F80_passing-brightgreen)](app/tests)

---

## 👥 Team Member Responsibilities

| Member | Branch | Responsibility |
|--------|--------|----------------|
| Member 1 | `feature/auth-jwt` | Auth, Users, Security, Config, Database |
| Member 2 | `feature/products-categories` | Products, Categories, Redis Caching |
| Member 3 | `feature/orders-cart` | Orders, Cart, Inventory Management |
| Member 4 | `feature/testing-dashboard` | pytest Suite, Logging, Monitoring Dashboard |

---

## 📁 Project Structure

```
ecommerce/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, middlewares, exception handlers
│   ├── config.py                  # pydantic-settings (env-driven)
│   ├── database.py                # SQLAlchemy engine + Session (SQLite & Postgres)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── dependencies.py        # Auth + role guards
│   │   ├── logging.py             # Loguru sinks + bounded request metrics
│   │   └── security.py            # bcrypt + JWT encode/decode
│   ├── models/                    # SQLAlchemy 2.0 ORM models
│   ├── schemas/                   # Pydantic v2 request/response schemas
│   ├── routes/                    # Thin FastAPI routers (one per resource)
│   ├── services/                  # Business logic (auth, product, order, cart, cache)
│   └── tests/                     # 80 pytest tests, runs against in-memory SQLite
├── migrations/                    # Alembic
├── frontend/
│   └── index.html                 # Single-file SPA client
├── .github/workflows/ci.yml       # Lint + test + docker-build on every push
├── Dockerfile                     # Multi-stage build, non-root user
├── docker-compose.yml             # API + Postgres + Redis with healthchecks
├── pytest.ini                     # Test discovery + warning filters
├── pyproject.toml                 # ruff + black config
├── requirements.txt
├── alembic.ini
└── .env.example                   # Template — copy to `.env`
```

---

## 🚀 How to Run

### Option A — Docker (Recommended)

```bash
cp .env.example .env       # then EDIT .env and set SECRET_KEY + FIRST_ADMIN_PASSWORD
docker compose up --build
```

- API docs: http://localhost:8000/docs
- Dashboard (admin only): http://localhost:8000/api/v1/dashboard/
- Frontend SPA: open `frontend/index.html` directly or serve via `python -m http.server 5500`

### Option B — Local

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Apply migrations (creates schema)
alembic upgrade head

# Run
uvicorn app.main:app --reload
```

---

## 🧪 Running Tests

Tests run against an **in-memory SQLite database** — no PostgreSQL or Redis needed.

```bash
DATABASE_URL=sqlite:///:memory: pytest -v
# or just:
pytest -v
```

With coverage:

```bash
pytest --cov=app --cov-report=term-missing
```

---

## 🔐 Default Admin Credentials

> ⚠️ Change these before any deployment. They are **for local development only**.

```
Email:    admin@ecommerce.com
Password: Admin@123456
```

---

## 📡 API Endpoints

### Authentication
| Method | Endpoint | Access |
|--------|----------|--------|
| POST | `/api/v1/auth/register` | Public |
| POST | `/api/v1/auth/login` | Public (rate-limited, 5/min/IP) |
| GET  | `/api/v1/auth/me` | Authenticated |

### Users
| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/api/v1/users` | Admin |
| GET | `/api/v1/users/{id}` | Admin |
| PUT | `/api/v1/users/{id}` | Admin or self |
| DELETE | `/api/v1/users/{id}` | Admin (soft delete) |

### Categories
| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/api/v1/categories` | Public |
| GET | `/api/v1/categories/{id}` | Public |
| POST | `/api/v1/categories` | Admin |
| PUT | `/api/v1/categories/{id}` | Admin |
| DELETE | `/api/v1/categories/{id}` | Admin |

### Products
| Method | Endpoint | Access | Notes |
|--------|----------|--------|-------|
| GET | `/api/v1/products` | Public | Pagination, search, price filter, category filter |
| GET | `/api/v1/products/{id}` | Public |  |
| POST | `/api/v1/products` | Admin |  |
| PUT | `/api/v1/products/{id}` | Admin |  |
| DELETE | `/api/v1/products/{id}` | Admin | Soft delete |

### Orders
| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/api/v1/orders` | Auth (customer sees own, admin sees all) |
| GET | `/api/v1/orders/{id}` | Auth (with ownership check) |
| POST | `/api/v1/orders` | Auth |
| PUT | `/api/v1/orders/{id}/status` | Admin |
| DELETE | `/api/v1/orders/{id}` | Auth (cancel + restore stock) |

### Cart (Redis-backed)
| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/api/v1/cart` | Auth |
| POST | `/api/v1/cart` | Auth |
| DELETE | `/api/v1/cart/{product_id}` | Auth |
| DELETE | `/api/v1/cart` | Auth (clear all) |

### Monitoring Dashboard (all admin-only)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/dashboard/` | HTML dashboard UI |
| GET | `/api/v1/dashboard/health` | DB + Redis health |
| GET | `/api/v1/dashboard/metrics` | Per-endpoint request metrics |
| GET | `/api/v1/dashboard/logs` | Recent log buffer |

---

## 🧱 Architecture Highlights

- **Layered**: thin routes → service functions → SQLAlchemy ORM, with Pydantic v2 schemas at the boundary.
- **Cache-Aside**: Redis-backed `get_*` paths with TTL; writes invalidate per-resource keys via SCAN.
- **Concurrency-safe stock**: `SELECT … FOR UPDATE` on the product row inside `place_order`.
- **Bounded telemetry**: request metrics use an LRU-bounded `OrderedDict`; log buffer is a fixed-size deque.
- **Driver-agnostic engine**: `database.py` switches kwargs based on the URL so the same code runs under SQLite (tests) and PostgreSQL (prod).
- **Rate limiting**: `slowapi` on `/auth/login`.
- **Structured logging**: console + rotating JSON file + error-only file + in-memory ring buffer.
- **Migrations**: Alembic, with an initial migration mirroring the ORM schema.

---

## 🔒 Security Notes

- bcrypt password hashing (passlib).
- JWT (HS256) with `iat`, `exp`, `sub`, `type` claims; `type` guard prevents refresh-as-access misuse.
- Role-based access control via `require_admin` dependency.
- CORS allow-list is explicit and driven by `CORS_ORIGINS` env var (no `*` in production).
- Admin dashboard HTML is admin-protected; tokens are kept in **sessionStorage** (per-tab) and never persisted across sessions.
- Rate limit on login mitigates brute-force.
- Order/stock operations are transactional; cancellations restore stock.
- `.env` and `logs/` are gitignored; `.dockerignore` keeps secrets and tests out of images.

---

## 🛠 Useful Commands

```bash
# Lint
ruff check app

# Format
ruff format app

# Test with coverage
pytest --cov=app --cov-report=term-missing

# Generate a new migration after editing models
alembic revision --autogenerate -m "describe change"

# Apply migrations
alembic upgrade head
```

