# AAU Grade Bot — Setup & Execution Guide

This document provides complete instructions for configuring, initializing, running, and testing **AAU Grade Bot** in local development and production environments.

---

## 1. Environment & System Requirements

- **Python**: 3.13+
- **PostgreSQL**: 15+ (Local instance or [Neon Serverless Postgres](https://neon.tech))
- **Redis** *(Optional but recommended)*: 7+ (For persistent FSM state and grade caching; falls back to in-memory mode if omitted)
- **Docker** *(Optional)*: Required for running Scenario D database stress tests via Testcontainers

---

## 2. Installation & Virtual Environment Setup

Clone the repository and install dependencies inside a Python virtual environment:

```bash
# Navigate to the project root
cd aau-grade-bot

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat
# Linux/macOS:
source .venv/bin/activate

# Upgrade pip and install requirements
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Environment Configuration (`.env`)

Create a `.env` file in the project root directory:

```ini
# Telegram Bot API Configuration
BOT_TOKEN=8750014906:AAXXXXXXXXXXXXXX_ExampleToken
ADMIN_TELEGRAM_ID=123456789

# Encryption Key for Passwords and Grades (AES-256-GCM Base64 Key)
ENCRYPTION_KEY=your_generated_base64_encryption_key_here

# PostgreSQL Database URL
# For Neon Pooler Endpoint (PgBouncer transaction mode):
DATABASE_URL=postgresql+asyncpg://user:pass@ep-cool-wind-123456-pooler.us-east-1.aws.neon.tech/neondb
# For Direct PostgreSQL Connection:
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/aau_grade_bot

# Redis URL (Optional - for persistent FSM & grade cache)
REDIS_URL=redis://localhost:6379/0

# Security Secrets for HTTP Endpoints
CRON_SECRET=super_secret_cron_token_here
METRICS_SECRET=super_secret_metrics_token_here

# Application Configuration
PORT=10000
ENVIRONMENT=development
PORTAL_SEMAPHORE_LIMIT=3
PORTAL_TIMEOUT_SECONDS=30
```

### Generating an AES-256-GCM Encryption Key

Run the following Python snippet to generate a secure 32-byte Base64-encoded key:

```bash
python -c "from crypto.cipher import AesGcmCipher; print(AesGcmCipher.generate_key())"
```

---

## 4. Database Setup & Migrations (Alembic)

The application uses SQLAlchemy (async) with Alembic for schema migrations.

```bash
# Run all pending migrations to bring the database schema up to date
alembic upgrade head

# Roll back the last migration (if needed)
alembic downgrade -1

# Create a new migration revision after modifying models
alembic revision --autogenerate -m "describe_changes"
```

---

## 5. Running the Application

### A. Running standard Telegram Bot & HTTP Server (Polling Mode)

```bash
python main.py
```

Upon startup, the application will:
1. Initialize the HTTP server on `http://0.0.0.0:10000`.
2. Connect to PostgreSQL via `database/connection.py` (auto-detecting Neon `-pooler` endpoints for `NullPool` vs direct `QueuePool`).
3. Connect to Redis for FSM state (or fall back to memory).
4. Start Telegram long polling for `/start`, `/register`, `/grades`, and `/metrics`.

### B. HTTP Endpoints & Operational Control

- **Health Check**: `GET /health` or `GET /` (Returns `204 No Content`)
- **Metrics Snapshot**: `GET /metrics` (Requires `X-Admin-Secret: <METRICS_SECRET>` header)
- **Trigger Cron Cohort Scan**: `POST /cron` (Requires `X-Cron-Secret: <CRON_SECRET>` header)

Example curl call for cron trigger:
```bash
curl -X POST http://localhost:10000/cron \
     -H "X-Cron-Secret: super_secret_cron_token_here"
```

---

## 6. Running Tests & Stress Suite

### A. Unit and Integration Test Suite (123 Tests)

Run the fast unit and integration tests:

```bash
python -m pytest tests/ --ignore=tests/stress -v
```

### B. Scalability & Stress Test Suite (Scenarios A–E up to 1,000 Users)

The stress testing suite evaluates throughput, latency, DB pool stability, and Telegram rate limit constraints.

```bash
# Run all stress tests using mocked backends (Scenarios A, B, C, E)
python -m pytest tests/stress/ -v -s -k "not scenario_d"

# Run Scenario D against a real PostgreSQL instance via Testcontainers (Docker required)
python -m pytest tests/stress/test_scenario_d_db_pool.py -v -s

# Run the complete stress suite (all scenarios including Docker)
python -m pytest tests/stress/ -v -s
```

---

## 7. Operational Troubleshooting

- **`DuplicatePreparedStatementError` or `InvalidSQLStatementNameError`**:
  Ensure your `DATABASE_URL` contains `-pooler` if connecting via Neon's PgBouncer endpoint. `database/connection.py` automatically configures `NullPool` and sets `statement_cache_size=0` when `-pooler` is present.
- **Telegram `HTTP 429 Too Many Requests`**:
  Telegram enforces a global ceiling of ~30 messages/second across all chats. High-volume notifications are paced accordingly.
