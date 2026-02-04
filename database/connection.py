import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# SQLAlchemy async requires the postgresql+asyncpg:// scheme.
# Render/Neon often provides postgres:// or postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# asyncpg doesn't support 'sslmode' or 'channel_binding' in the query string.
# We need to strip these if they exist to avoid TypeError.
if "?" in DATABASE_URL:
    base_url, query = DATABASE_URL.split("?", 1)
    from urllib.parse import parse_qs, urlencode
    params = parse_qs(query)
    # Remove asyncpg-incompatible params
    params.pop("sslmode", None)
    params.pop("channel_binding", None)
    # Rebuild URL
    new_query = urlencode(params, doseq=True)
    DATABASE_URL = f"{base_url}?{new_query}" if new_query else base_url

# For Neon/Render, we enforce SSL and disable statement caching to prevent stale plans during migrations
engine = create_async_engine(
    DATABASE_URL, 
    connect_args={
        "ssl": True if "neon.tech" in DATABASE_URL else False,
        "prepared_statement_cache_size": 0 
    },
    pool_recycle=300,        # Recycle connections every 5 mins
    pool_pre_ping=True,      # Check connection health before use
    echo=True
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    async with SessionLocal() as session:
        yield session
