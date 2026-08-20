"""SQLAlchemy implementation of campus persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Campus


class SqlAlchemyCampusRepository:
    """Repository for campus persistence operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(self) -> list[Campus]:
        statement = select(Campus)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
