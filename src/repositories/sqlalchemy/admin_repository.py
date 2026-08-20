"""SQLAlchemy implementation for admin operations."""

from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, Department


class SqlAlchemyAdminRepository:
    """Repository for admin queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_system_metrics(self) -> dict:
        """Fetch system-wide metrics."""
        # Active users count
        stmt = select(func.count(User.id))
        result = await self.session.execute(stmt)
        total_users = result.scalar_one_or_none() or 0

        # Users by department
        stmt_dept = select(User.department_id, func.count(User.id)).group_by(User.department_id)
        result_dept = await self.session.execute(stmt_dept)
        users_by_dept = {row[0] or "Unknown": row[1] for row in result_dept.all()}

        return {
            "total_users": total_users,
            "users_by_department": users_by_dept
        }
