"""Account inactivity and deletion workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dto.bot import AccountDeletionRequest


@dataclass(frozen=True)
class AccountLifecycleResult:
    message: str
    deleted: bool = False


class AccountLifecycleService:
    """Handle inactivity notices, self-deletion, and audit cleanup.

    The implementation stays small for Phase 6 and exposes the hooks needed by the
    handler layer and future background jobs.
    """

    def __init__(self, user_repository: Any | None = None, audit_repository: Any | None = None, notifier: Any | None = None) -> None:
        self.user_repository = user_repository
        self.audit_repository = audit_repository
        self.notifier = notifier

    async def request_deletion(self, request: AccountDeletionRequest) -> AccountLifecycleResult:
        if not request.confirm:
            return AccountLifecycleResult(message="Confirmation required before deletion")
        if self.user_repository is not None:
            user = None
            if hasattr(self.user_repository, "get_by_telegram_id"):
                user = await self.user_repository.get_by_telegram_id(request.telegram_id)
            if user is not None and hasattr(self.user_repository, "remove"):
                await self.user_repository.remove(user)
        if self.audit_repository is not None:
            await self.audit_repository.add(
                {
                    "telegram_id": request.telegram_id,
                    "action": "account_deletion_requested",
                    "details": {"confirmed": True},
                }
            )
        return AccountLifecycleResult(message="Account deletion queued", deleted=True)
