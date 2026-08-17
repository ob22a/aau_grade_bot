"""Admin operations service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dto.bot import BroadcastRequest, SettingsUpdateRequest, MetricsSnapshot


@dataclass(frozen=True)
class BroadcastResult:
    message: str
    recipients: int = 0


@dataclass(frozen=True)
class SettingsUpdateResult:
    message: str


class AdminService:
    """Handle admin-only broadcast and settings workflows."""

    def __init__(self, notifier: Any | None = None, settings_repository: Any | None = None, metrics: Any | None = None) -> None:
        self.notifier = notifier
        self.settings_repository = settings_repository
        self.metrics = metrics

    async def broadcast(self, request: BroadcastRequest) -> BroadcastResult:
        recipients = 0
        if self.notifier is not None and request.recipient_ids:
            for telegram_id in request.recipient_ids:
                await self.notifier.send_message(telegram_id, request.message)
                recipients += 1
        elif self.notifier is not None:
            await self.notifier.send_admin(request.message)
            recipients = 1
        return BroadcastResult(message="Broadcast sent", recipients=recipients)

    async def update_setting(self, request: SettingsUpdateRequest) -> SettingsUpdateResult:
        if not request.confirm:
            return SettingsUpdateResult(message="Confirmation required before changing settings")
        if self.settings_repository is not None:
            await self.settings_repository.set(request.key, request.value)
        return SettingsUpdateResult(message=f"Setting {request.key} updated")

    async def metrics_snapshot(self) -> MetricsSnapshot:
        if self.metrics is not None:
            return await self.metrics.snapshot()
        return MetricsSnapshot(uptime_seconds=0)
