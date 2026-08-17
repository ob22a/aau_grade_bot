"""SQLAlchemy implementation for semester result persistence."""

from __future__ import annotations

from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SemesterResult


class SqlAlchemySemesterResultRepository:
    """Repository for encrypted semester result documents."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: str) -> List[SemesterResult]:
        statement = select(SemesterResult).where(SemesterResult.user_id == user_id)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def add(self, semester_result: SemesterResult) -> None:
        self.session.add(semester_result)

    async def remove(self, semester_result: SemesterResult) -> None:
        await self.session.delete(semester_result)
