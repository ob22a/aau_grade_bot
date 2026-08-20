from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Department

class SqlAlchemyDepartmentRepository:
    """SQLAlchemy implementation of DepartmentRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, department_id: str) -> Any | None:
        return await self._session.get(Department, department_id)

    async def get_by_name(self, full_name: str) -> Any | None:
        stmt = select(Department).where(Department.full_name == full_name)
        return await self._session.scalar(stmt)

    async def get_by_name_and_campus(self, full_name: str, campus_id: str) -> Any | None:
        stmt = select(Department).where(Department.full_name == full_name, Department.campus_id == campus_id)
        return await self._session.scalar(stmt)

    async def add(self, department: Any) -> None:
        self._session.add(department)
