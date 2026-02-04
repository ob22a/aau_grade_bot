import logging
from sqlalchemy import text
from database.connection import engine

logger = logging.getLogger(__name__)

async def run_migrations():
    """
    Safely adds missing encryption columns to the database.
    This is idempotent and safe to run on every startup.
    """
    logger.info("🚀 Checking database schema for encryption columns...")
    
    async with engine.begin() as conn:
        try:
            # 1. Add IV column to grades
            await conn.execute(text("ALTER TABLE grades ADD COLUMN IF NOT EXISTS iv VARCHAR(255)"))
            
            # 2. Add IV and Encrypted Data to assessments
            await conn.execute(text("ALTER TABLE assessments ADD COLUMN IF NOT EXISTS iv VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE assessments ADD COLUMN IF NOT EXISTS encrypted_data TEXT"))
            
            # 3. Add IV column to semester_results
            await conn.execute(text("ALTER TABLE semester_results ADD COLUMN IF NOT EXISTS iv VARCHAR(255)"))
            
            # 4. Ensure user_credentials has IV
            await conn.execute(text("ALTER TABLE user_credentials ADD COLUMN IF NOT EXISTS iv VARCHAR(255)"))
            
            logger.info("✅ Database schema is up-to-date.")
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            # We don't raise here to allow the bot to attempt to start regardless,
            # though SQL errors will likely happen later if this failed.
