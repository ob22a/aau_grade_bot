"""Telegram notification sender adapter."""

from __future__ import annotations

import logging
from aiogram import Bot

logger = logging.getLogger(__name__)

class AiogramTelegramNotificationSender:
    def __init__(self, bot: Bot | None, admin_telegram_ids: list[int] | None = None) -> None:
        self.bot = bot
        self.admin_telegram_ids = admin_telegram_ids or []

    async def send_message(self, telegram_id: int, text: str) -> None:
        if self.bot:
            try:
                await self.bot.send_message(telegram_id, text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to send message to {telegram_id}: {e}")

    async def send_admin_alert(self, text: str) -> None:
        if self.bot:
            for admin_id in self.admin_telegram_ids:
                try:
                    await self.bot.send_message(admin_id, f"🚨 Admin Alert:\n{text}", parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to send admin alert to {admin_id}: {e}")
