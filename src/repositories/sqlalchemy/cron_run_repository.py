"""SQLAlchemy implementation for cron run persistence."""

from __future__ import annotations

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import CronRun


class SqlAlchemyCronRunRepository:
    """Repository for cron run history."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, cron_run: CronRun) -> None:
        self.session.add(cron_run)

    async def get_by_id(self, run_id: str) -> Optional[CronRun]:
        return await self.session.get(CronRun, run_id)
