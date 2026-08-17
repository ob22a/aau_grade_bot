"""SQLAlchemy implementation for audit log persistence."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditLog


class SqlAlchemyAuditLogRepository:
    """Repository for audit log storage."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, audit_log: AuditLog) -> None:
        self.session.add(audit_log)
