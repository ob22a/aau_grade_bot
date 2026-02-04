import logging
from sqlalchemy import text
from database.connection import engine

logger = logging.getLogger(__name__)

async def run_migrations():
    """
    Safely adds missing encryption columns and widens existing columns
    to accommodate longer encrypted strings.
    """
    logger.info("🚀 Checking database schema for encryption compatibility...")
    
    async with engine.begin() as conn:
        try:
            # 1. Ensure IV columns exist
            await conn.execute(text("ALTER TABLE grades ADD COLUMN IF NOT EXISTS iv VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE assessments ADD COLUMN IF NOT EXISTS iv VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE assessments ADD COLUMN IF NOT EXISTS encrypted_data TEXT"))
            await conn.execute(text("ALTER TABLE semester_results ADD COLUMN IF NOT EXISTS iv VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE user_credentials ADD COLUMN IF NOT EXISTS iv VARCHAR(255)"))
            
            # 2. Widen columns that will store encrypted data
            # grades table
            await conn.execute(text("ALTER TABLE grades ALTER COLUMN grade TYPE VARCHAR(512)"))
            await conn.execute(text("ALTER TABLE grades ALTER COLUMN course_name TYPE VARCHAR(512)"))
            await conn.execute(text("ALTER TABLE grades ALTER COLUMN credit_hour TYPE VARCHAR(512)"))
            await conn.execute(text("ALTER TABLE grades ALTER COLUMN ects TYPE VARCHAR(512)"))
            
            # semester_results table
            await conn.execute(text("ALTER TABLE semester_results ALTER COLUMN sgpa TYPE VARCHAR(512)"))
            await conn.execute(text("ALTER TABLE semester_results ALTER COLUMN cgpa TYPE VARCHAR(512)"))
            await conn.execute(text("ALTER TABLE semester_results ALTER COLUMN status TYPE VARCHAR(512)"))
            
            logger.info("✅ Database schema is compatible with encryption.")
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            # If migration fails, it might be because the database is not PostgreSQL
            # but since Render uses Postgres, this should work.
