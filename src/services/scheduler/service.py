"""Cron and cohort scan orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class SchedulerRunResult:
    started_at: datetime
    finished_at: datetime | None = None
    skipped: bool = False
    message: str = ""


class SchedulerService:
    """Manage atomic cron runs and cohort scan sequencing."""

    def __init__(
        self,
        lock: Any | None = None,
        notification_service: Any | None = None,
        portal_client: Any | None = None,
        session_factory: Any | None = None,
        cipher: Any | None = None,
    ) -> None:
        self.lock = lock
        self.notification_service = notification_service
        self.portal_client = portal_client
        self.session_factory = session_factory
        self.cipher = cipher

    async def run_once(self) -> SchedulerRunResult:
        started_at = datetime.now(timezone.utc)
        lock_key = "cron:run"
        if self.lock is not None:
            acquired = await self.lock.acquire(lock_key, ttl_seconds=3600)
            if not acquired:
                return SchedulerRunResult(
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    skipped=True,
                    message="Cron already running",
                )

        try:
            return SchedulerRunResult(started_at=started_at, finished_at=datetime.now(timezone.utc), message="Cron finished")
        finally:
            if self.lock is not None:
                await self.lock.release(lock_key)
