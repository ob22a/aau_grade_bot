"""SQLAlchemy implementation of user persistence."""

from __future__ import annotations

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User


class SqlAlchemyUserRepository:
    """Repository for user persistence operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: str) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        statement = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def get_by_university_id(self, university_id: str) -> Optional[User]:
        statement = select(User).where(User.university_id == university_id)
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def add(self, user: User) -> None:
        self.session.add(user)

    async def remove(self, user: User) -> None:
        await self.session.delete(user)

    async def get_all_users(self) -> list[User]:
        statement = select(User)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_inactive_users(self, threshold_date) -> list[User]:
        statement = select(User).where(User.last_used < threshold_date)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
