import html
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update

from config import Settings
from services.container import ApplicationServices


class MaintenanceMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings, services: ApplicationServices):
        self.settings = settings
        self.services = services

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        user = None
        if event.message:
            user = event.message.from_user
        elif event.callback_query:
            user = event.callback_query.from_user

        if user and user.id not in self.settings.admins_telegram_id:
            settings_dict = await self.services.admin.get_all_settings()
            if settings_dict.get("is_maintenance_mode", "false").lower() == "true":
                msg = "🛠 <b>Bot is currently under maintenance.</b>\n\nPlease try again later."
                if event.message:
                    await event.message.answer(msg)
                elif event.callback_query:
                    if event.callback_query.message:
                        await event.callback_query.message.answer(msg)
                    await event.callback_query.answer("Under maintenance", show_alert=True)
                return

        return await handler(event, data)
