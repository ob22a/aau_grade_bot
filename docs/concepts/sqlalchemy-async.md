# SQLAlchemy async in this project

The repository uses SQLAlchemy's asyncio extension to talk to PostgreSQL without blocking the event loop.

## Core pieces

- `database/connection.py` creates the async engine and session factory.
- `database/unit_of_work.py` owns one `AsyncSession` per use case.
- `database/models.py` defines the ORM schema.
- `repositories/sqlalchemy/*` provides concrete repository implementations.

## Why async matters

Telegram handlers, cron workers, and portal scrapes all run in an async application. Using synchronous database calls would block the event loop and reduce throughput.

## Session ownership rules

- One `AsyncSession` belongs to one Unit of Work.
- The session is created inside the UoW and closed on exit.
- Repositories receive the session; they never create or close sessions.
- Sessions are never shared across concurrent tasks.

These rules are captured in ADR 015 and are part of the connection-safety story for the project.

## Connection safety

`create_async_engine` is configured differently based on whether the database URL points to a Neon pooler endpoint or a direct connection:

- **Pooler endpoint** (`-pooler` in hostname): Uses `NullPool` and disables asyncpg statement caching (`statement_cache_size=0`) to avoid `DuplicatePreparedStatementError` under PgBouncer transaction pooling.
- **Direct connection**: Uses standard `QueuePool` with `pool_pre_ping=True` and `pool_recycle=300`.

See [Connection Pooling](./connection-pooling.md) for the full explanation of why this matters and what each setting does.

## Mapping style

- Primary keys and foreign keys are modeled with SQLAlchemy ORM columns.
- Timestamps use `timezone=True`.
- Enum columns store Python enum member names.
- Sensitive grade and credential fields are stored as encrypted blobs.

## Repository pattern

Repositories expose task-specific methods such as:

- `get_by_telegram_id`
- `get_by_user_id`
- `add`
- `remove`

The rest of the application works against those repository contracts instead of raw ORM operations.
