from __future__ import annotations
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

INCOMPATIBLE_ASYNCPG_PARAMETERS = frozenset({"sslmode", "channel_binding"})


def _is_pooler_url(url: str) -> bool:
    """Detect Neon pooler endpoints (contain '-pooler' in hostname)."""
    return "-pooler" in url


def clean_async_database_url(url: Optional[str]) -> Optional[str]:
    """Convert a PostgreSQL URL to asyncpg format and remove unsupported options."""
    if not url:
        return url

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlparse(url)
    parameters = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in INCOMPATIBLE_ASYNCPG_PARAMETERS
    ]
    return urlunparse(parsed._replace(query=urlencode(parameters, doseq=True)))


def create_engine_from_url(database_url: str) -> AsyncEngine:
    """Build a resilient async engine compatible with Neon/PgBouncer pooler endpoints.
    """
    cleaned_url = clean_async_database_url(database_url)
    if not cleaned_url:
        raise ValueError("DATABASE_URL is required to create a database engine")

    using_pooler = _is_pooler_url(cleaned_url)

    if using_pooler:
        return create_async_engine(
            cleaned_url,
            poolclass=NullPool,
            connect_args={
                "ssl": True,
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
        )
    
    return create_async_engine(
        cleaned_url,
        connect_args={"ssl": True},
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the session factory injected into Units of Work."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
