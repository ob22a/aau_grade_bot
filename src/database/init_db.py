import asyncio
import logging

from database.connection import engine
from database.models import Base


async def init_db() -> None:
    """Create all database tables from SQLAlchemy metadata."""
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