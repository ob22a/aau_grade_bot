from sqlalchemy.ext.asyncio import AsyncSession
from database.models import AuditLog
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def log(self, action: str, telegram_id: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None, source: str = "telegram_bot"):
        try:
            log_entry = AuditLog(
                telegram_id=telegram_id,
                action=action,
                metadata_json=metadata,
                source=source
            )
            self.db.add(log_entry)
            # We don't necessarily want to wait/commit here if it's called from a larger transaction
            # but for simplicity in this prototype we'll let the caller commit.
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
