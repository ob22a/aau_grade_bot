"""Notification orchestration service."""

from __future__ import annotations

from typing import Any


class NotificationService:
    def __init__(self, sender: Any | None = None) -> None:
        self.sender = sender

    async def send_user(self, telegram_id: int, text: str) -> None:
        if self.sender is not None:
            await self.sender.send_message(telegram_id, text)

    async def send_admin(self, text: str) -> None:
        if self.sender is not None:
            await self.sender.send_admin_alert(text)
