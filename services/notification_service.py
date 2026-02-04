import os
from aiogram import Bot
import logging

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, bot_token: str = None):
        token = bot_token or os.getenv("BOT_TOKEN")
        if not token:
            logger.error("BOT_TOKEN not found for NotificationService")
            self.bot = None
        else:
            self.bot = Bot(token=token)

    async def send_notification(self, telegram_id: int, message: str):
        if not self.bot:
            logger.error(f"Cannot send notification to {telegram_id}: Bot not initialized")
            return

        try:
            await self.bot.send_message(chat_id=telegram_id, text=message, parse_mode="HTML")
            logger.info(f"Notification sent to {telegram_id}")
        except Exception as e:
            logger.error(f"Failed to send notification to {telegram_id}: {e}")

    async def close(self):
        if self.bot:
            await self.bot.session.close()
