"""SQLAlchemy implementation for assessment persistence."""

from __future__ import annotations

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Assessment


class SqlAlchemyAssessmentRepository:
    """Repository for storing encrypted assessment details."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_course_id(self, user_course_id: str) -> Optional[Assessment]:
        statement = select(Assessment).where(Assessment.user_course_id == user_course_id)
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def add(self, assessment: Assessment) -> None:
        self.session.add(assessment)

    async def remove_by_user_course_id(self, user_course_id: str) -> None:
        assessment = await self.get_by_user_course_id(user_course_id)
        if assessment is not None:
            await self.session.delete(assessment)
