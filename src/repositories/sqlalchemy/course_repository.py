from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Course

class SqlAlchemyCourseRepository:
    """SQLAlchemy implementation of CourseRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, course_id: str) -> Any | None:
        return await self._session.get(Course, course_id)

    async def add(self, course: Any) -> None:
        self._session.add(course)
