"""Admin operations service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dto.bot import BroadcastRequest, SettingsUpdateRequest, MetricsSnapshot


@dataclass(frozen=True)
class BroadcastResult:
    """Result of an admin broadcast operation."""
    message: str
    recipients: int = 0


@dataclass(frozen=True)
class SettingsUpdateResult:
    """Result of an admin settings update operation."""
    message: str


class AdminService:
    """Handle admin-only broadcast and settings workflows."""

    def __init__(self, notifier: Any | None = None, settings_repository: Any | None = None, metrics: Any | None = None, session_factory: Any | None = None) -> None:
        self.notifier = notifier
        self.settings_repository = settings_repository
        self.metrics = metrics
        self.session_factory = session_factory

    async def broadcast(self, request: BroadcastRequest) -> BroadcastResult:
        """
        Broadcasts a message to a list of target telegram IDs.
        If no target IDs are provided, it broadcasts to all registered users.
        """
        recipients = 0
        target_ids = request.recipient_ids or []
        
        # If no explicit recipients provided, fetch all users from the DB
        if not target_ids and self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                all_users = await uow.users.get_all_users()
                target_ids = [u.telegram_id for u in all_users]
        
        if self.notifier is not None and target_ids:
            for telegram_id in target_ids:
                try:
                    await self.notifier.send_message(telegram_id, request.message)
                    recipients += 1
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to send broadcast to {telegram_id}: {e}")
        elif self.notifier is not None:
            await self.notifier.send_admin(request.message)
            recipients = 1
            
        return BroadcastResult(message=f"Broadcast sent to {recipients} users", recipients=recipients)

    async def update_setting(self, request: SettingsUpdateRequest) -> SettingsUpdateResult:
        """Updates a global system setting in the database."""
        if not request.confirm:
            return SettingsUpdateResult(message="Confirmation required before changing settings")
            
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                await uow.settings.set(request.key, request.value)
                await uow.commit()
            return SettingsUpdateResult(message=f"Setting {request.key} updated")
            
        if self.settings_repository is not None:
            await self.settings_repository.set(request.key, request.value)
            return SettingsUpdateResult(message=f"Setting {request.key} updated")
            
        return SettingsUpdateResult(message="Failed: No repository configured")

    async def get_all_settings(self) -> dict[str, str]:
        """Returns all system settings from the database."""
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                return await uow.settings.get_all()
        return {}

    async def metrics_snapshot(self) -> MetricsSnapshot:
        """Generates a snapshot of current system metrics and active user counts."""
        if self.metrics is not None:
            return await self.metrics.snapshot()
            
        active_users = 0
        details = {}
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            try:
                async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                    metrics = await uow.admin.get_system_metrics()
                    active_users = metrics.get("total_users", 0)
                    details["users_by_department"] = metrics.get("users_by_department", {})
            except Exception as e:
                import html
                details["db_error"] = html.escape(str(e))
                
        import time
        import psutil
        uptime_seconds = int(time.time() - psutil.Process().create_time())
        
        return MetricsSnapshot(
            uptime_seconds=uptime_seconds,
            active_users=active_users,
            details=details
        )
