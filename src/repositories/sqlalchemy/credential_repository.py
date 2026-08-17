"""SQLAlchemy implementation for user credentials persistence."""

from __future__ import annotations

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import UserCredential


class SqlAlchemyUserCredentialRepository:
    """Repository for storing encrypted user credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: str) -> Optional[UserCredential]:
        statement = select(UserCredential).where(UserCredential.user_id == user_id)
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def add(self, credential: UserCredential) -> None:
        self.session.add(credential)

    async def remove_by_user_id(self, user_id: str) -> None:
        credential = await self.get_by_user_id(user_id)
        if credential is not None:
            await self.session.delete(credential)
