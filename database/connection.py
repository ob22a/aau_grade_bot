import sys
import logging
from config import DATABASE_URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

"""
Cleans up database url into async engine friendly format
"""
def clean_async_database_url(url: str) -> str:
    if not url:
        return url
        
    # Standardize the scheme for asyncpg
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    # Clean up asyncpg-incompatible query parameters
    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query)
        params.pop("sslmode", None)
        params.pop("channel_binding", None)
        new_query = urlencode(params, doseq=True)
        parsed = parsed._replace(query=new_query)
        
    return urlunparse(parsed)


logger = logging.getLogger(__name__)

if not DATABASE_URL:
  logger.critical("Missing Database URL in the environment variable. Exiting code")
  sys.exit(1)

# No need for try catch block because the engine is lazy and connection won't be made rightaway 

engine=create_async_engine(
  clean_async_database_url(DATABASE_URL),
  connect_args={
    "ssl":True
  },
  pool_recycle=300,
  pool_pre_ping=True
)

SessionLocal = async_sessionmaker(
  bind=engine,
  class_=AsyncSession,
  expire_on_commit=False
)