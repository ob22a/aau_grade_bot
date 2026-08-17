"""SQLAlchemy implementation for user course persistence."""

from __future__ import annotations

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import UserCourse


class SqlAlchemyUserCourseRepository:
    """Repository for user course enrollment and grade metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: str) -> List[UserCourse]:
        statement = select(UserCourse).where(UserCourse.user_id == user_id)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def add(self, user_course: UserCourse) -> None:
        self.session.add(user_course)

    async def remove(self, user_course: UserCourse) -> None:
        await self.session.delete(user_course)
