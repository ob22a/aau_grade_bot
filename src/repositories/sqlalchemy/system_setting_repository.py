"""SQLAlchemy implementation for system settings persistence."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SystemSetting


class SqlAlchemySystemSettingRepository:
    """Repository for key/value settings storage."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        statement = select(SystemSetting).where(SystemSetting.key == key)
        result = await self.session.execute(statement)
        setting = result.scalars().first()
        return setting.value if setting is not None else None

    async def set(self, key: str, value: str) -> None:
        statement = select(SystemSetting).where(SystemSetting.key == key)
        result = await self.session.execute(statement)
        setting = result.scalars().first()
        if setting is None:
            self.session.add(SystemSetting(key=key, value=value))
        else:
            await self.session.execute(
                update(SystemSetting)
                .where(SystemSetting.key == key)
                .values(value=value)
            )
