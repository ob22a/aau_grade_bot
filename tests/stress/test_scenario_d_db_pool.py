"""Stress Scenario D: Database Connection Pool Under Real PostgreSQL.

Uses testcontainers to spin up a real PostgreSQL instance and tests the
SQLAlchemy engine configuration under concurrent load. This is the ONLY
way to catch the asyncpg/PgBouncer prepared-statement bug that mocked
backends cannot reproduce.

Requires Docker. Skipped if Docker is unavailable.
"""

from __future__ import annotations

import asyncio
import time
import os

import pytest

from tests.stress.conftest import StressMetrics


# Skip if Docker is not available or testcontainers not installed
try:
    from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False

# Also skip if explicitly disabled (e.g. in CI without Docker)
SKIP_DOCKER = os.environ.get("SKIP_DOCKER_TESTS", "").lower() in ("1", "true", "yes")

pytestmark = pytest.mark.skipif(
    not HAS_TESTCONTAINERS or SKIP_DOCKER,
    reason="Requires testcontainers[postgres] and Docker",
)


RAPID_CYCLE_COUNTS = [50, 100, 200, 500]


def _make_async_url(sync_url: str) -> str:
    """Convert testcontainers sync URL to asyncpg URL."""
    return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "psycopg2://", "asyncpg://", 1
    )


@pytest.fixture(scope="module")
def postgres_url():
    """Start a real PostgreSQL container for the test module."""
    with PostgresContainer("postgres:15-alpine") as container:
        url = container.get_connection_url()
        yield _make_async_url(url)


@pytest.mark.parametrize("cycle_count", RAPID_CYCLE_COUNTS)
def test_scenario_d_rapid_session_cycles(postgres_url: str, cycle_count: int) -> None:
    """Rapid open/execute/close cycles to verify zero connection leaks."""

    async def scenario() -> None:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from sqlalchemy import text

        # Use the SAME config as production (but without SSL for local container)
        engine = create_async_engine(
            postgres_url,
            connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        metrics = StressMetrics()
        metrics.start_time = time.perf_counter()

        async def rapid_cycle(idx: int) -> None:
            t0 = time.perf_counter()
            try:
                async with session_factory() as session:
                    result = await session.execute(text("SELECT 1 AS health"))
                    row = result.scalar()
                    assert row == 1
                metrics.record_latency(time.perf_counter() - t0)
            except Exception as exc:
                metrics.record_error(exc)

        tasks = [rapid_cycle(i) for i in range(cycle_count)]
        await asyncio.gather(*tasks)

        metrics.end_time = time.perf_counter()
        print(metrics.summary(f"Scenario D: {cycle_count} Rapid Session Cycles"))

        # Zero errors — this catches DuplicatePreparedStatementError
        assert metrics.error_count == 0, (
            f"{metrics.error_count} errors: {[type(e).__name__ for e in metrics.errors[:5]]}"
        )
        assert metrics.success_count == cycle_count

        # Verify no connection leaks
        pool = engine.pool
        assert pool.checkedout() == 0, f"Connection leak: {pool.checkedout()} checked out"

        await engine.dispose()

    asyncio.run(scenario())


def test_scenario_d_concurrent_table_operations(postgres_url: str) -> None:
    """Create table, insert/read concurrently, verify data integrity."""

    async def scenario() -> None:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from sqlalchemy import text

        engine = create_async_engine(
            postgres_url,
            connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
            pool_size=5,
            max_overflow=10,
        )
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # Create test table
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS stress_test_users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    name TEXT NOT NULL
                )
            """))
            await conn.execute(text("TRUNCATE stress_test_users"))

        metrics = StressMetrics()
        metrics.start_time = time.perf_counter()
        insert_count = 200

        async def insert_user(idx: int) -> None:
            t0 = time.perf_counter()
            try:
                async with session_factory() as session:
                    async with session.begin():
                        await session.execute(
                            text("INSERT INTO stress_test_users (telegram_id, name) VALUES (:tid, :name)"),
                            {"tid": 50000 + idx, "name": f"user_{idx}"},
                        )
                metrics.record_latency(time.perf_counter() - t0)
            except Exception as exc:
                metrics.record_error(exc)

        tasks = [insert_user(i) for i in range(insert_count)]
        await asyncio.gather(*tasks)
        metrics.end_time = time.perf_counter()

        print(metrics.summary(f"Scenario D: {insert_count} Concurrent Inserts"))

        # Verify all inserts succeeded
        assert metrics.error_count == 0
        assert metrics.success_count == insert_count

        # Verify data integrity — count should match
        async with session_factory() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM stress_test_users"))
            count = result.scalar()
            assert count == insert_count, f"Expected {insert_count} rows, got {count}"

        # Cleanup
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS stress_test_users"))

        await engine.dispose()

    asyncio.run(scenario())
