import asyncio
import logging

from database.connection import create_engine_from_url
from config import load_settings
from database.models import Base


async def init_db() -> None:
    """Create all database tables from SQLAlchemy metadata."""
    settings = load_settings()
    engine = create_engine_from_url(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(init_db())
        logging.info("Database tables created successfully.")
    except Exception:
        logging.exception("Failed to create database tables.")
        raise