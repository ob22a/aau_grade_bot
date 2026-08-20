"""Admin command handlers."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from dto.bot import BroadcastRequest, SettingsUpdateRequest
from fsm.states import AdminBroadcastFSM
from services.container import ApplicationServices


from aiogram.filters import Command, BaseFilter
from config import Settings

class AdminFilter(BaseFilter):
    def __init__(self, admin_ids: list[int] | None):
        self.admin_ids = admin_ids or []

    async def __call__(self, message: Message) -> bool:
        return message.from_user and message.from_user.id in self.admin_ids

def build_admin_router(settings: Settings, services: ApplicationServices) -> Router:
    """Builds and registers all admin-only commands and states."""
    router = Router()
    router.message.filter(AdminFilter(settings.admins_telegram_id))

    @router.message(Command("broadcast"))
    async def begin_broadcast(message: Message, state: FSMContext) -> None:
        """Starts the broadcast workflow by asking for the message text."""
        await state.clear()
        await state.set_state(AdminBroadcastFSM.message)
        await message.answer("Send the broadcast text.\n\n<i>(Send /cancel to abort)</i>")

    @router.message(AdminBroadcastFSM.message)
    async def capture_broadcast(message: Message, state: FSMContext) -> None:
        """Receives the broadcast text and sends it to all users."""
        text = message.text or ""
        if text.startswith("/"):
            await state.clear()
            if text.startswith("/cancel"):
                await message.answer("Broadcast cancelled.")
            else:
                await message.answer(f"Broadcast cancelled because you sent '{text}'.")
            return

        request = BroadcastRequest(
            admin_telegram_id=message.from_user.id if message.from_user else 0,
            message=text,
        )
        try:
            result = await services.admin.broadcast(request)
            await state.clear()
            await message.answer(result.message)
        except Exception as exc:
            await state.clear()
            await message.answer(f"❌ Broadcast failed: {html.escape(str(exc))}")

    @router.message(Command("metrics"))
    async def metrics(message: Message, state: FSMContext) -> None:
        """Shows system uptime and active user counts."""
        await state.clear()
        try:
            snapshot = await services.admin.metrics_snapshot()
            
            msg = (
                f"📊 <b>Bot Metrics</b>\n\n"
                f"⏱ <b>Uptime:</b> {snapshot.uptime_seconds}s\n"
                f"👥 <b>Active Users:</b> {snapshot.active_users}\n"
                f"🔄 <b>Scrape Attempts:</b> {snapshot.scrape_attempts}\n"
                f"❌ <b>Scrape Failures:</b> {snapshot.scrape_failures}\n"
            )
            if snapshot.details:
                msg += f"\n<b>Details:</b>\n"
                for k, v in snapshot.details.items():
                    msg += f"• {html.escape(str(k))}: {html.escape(str(v))}\n"
                    
            await message.answer(msg)
        except Exception as exc:
            await message.answer(f"❌ Failed to fetch metrics: {html.escape(str(exc))}")

    @router.message(Command("setsetting"))
    async def set_setting(message: Message, state: FSMContext) -> None:
        await state.clear()
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Usage: /setsetting &lt;key&gt; &lt;value&gt;")
            return
        request = SettingsUpdateRequest(
            admin_telegram_id=message.from_user.id if message.from_user else 0,
            key=parts[1],
            value=parts[2],
            confirm=True,
        )
        try:
            result = await services.admin.update_setting(request)
            await message.answer(result.message)
        except Exception as exc:
            await message.answer(f"❌ Failed to update setting: {html.escape(str(exc))}")

    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext) -> None:
        await state.clear()
        try:
            # We can check the DB for the setting if needed, but for now we'll just show the menu.
            await message.answer(
                f"🛠 <b>Admin Dashboard</b>\n\n"
                "Commands:\n"
                "/settings - View all current settings\n"
                "/setsetting &lt;key&gt; &lt;value&gt; - Update a setting\n"
                "/metrics - View bot metrics\n"
                "/broadcast - Send a broadcast message\n"
                "/start_service - Enable grade checking service\n"
                "/stop_service - Disable grade checking service\n"
                "/maintenance_on - Enable maintenance mode\n"
                "/maintenance_off - Disable maintenance mode"
            )
        except Exception as exc:
            await message.answer(f"❌ Failed to load admin dashboard: {html.escape(str(exc))}")

    @router.message(Command("settings"))
    async def view_settings(message: Message, state: FSMContext) -> None:
        """Shows all system settings."""
        await state.clear()
        try:
            settings_dict = await services.admin.get_all_settings()
            if not settings_dict:
                await message.answer("No settings found in the database.")
                return
            
            msg = "⚙️ <b>Current System Settings:</b>\n\n"
            for k, v in settings_dict.items():
                msg += f"• <b>{html.escape(str(k))}</b>: <code>{html.escape(str(v))}</code>\n"
            await message.answer(msg)
        except Exception as exc:
            await message.answer(f"❌ Failed to fetch settings: {html.escape(str(exc))}")

    @router.message(Command("start_service"))
    async def cmd_start_service(message: Message, state: FSMContext) -> None:
        await state.clear()
        request = SettingsUpdateRequest(
            admin_telegram_id=message.from_user.id if message.from_user else 0,
            key="is_scheduling_enabled",
            value="true",
            confirm=True,
        )
        try:
            result = await services.admin.update_setting(request)
            await message.answer("✅ Grade checking service <b>ENABLED</b>.")
        except Exception as exc:
            await message.answer(f"❌ Failed to enable service: {html.escape(str(exc))}")

    @router.message(Command("stop_service"))
    async def cmd_stop_service(message: Message, state: FSMContext) -> None:
        await state.clear()
        request = SettingsUpdateRequest(
            admin_telegram_id=message.from_user.id if message.from_user else 0,
            key="is_scheduling_enabled",
            value="false",
            confirm=True,
        )
        try:
            result = await services.admin.update_setting(request)
            await message.answer("🛑 Grade checking service <b>DISABLED</b>.")
        except Exception as exc:
            await message.answer(f"❌ Failed to disable service: {html.escape(str(exc))}")

    @router.message(Command("maintenance_on"))
    async def cmd_maintenance_on(message: Message, state: FSMContext) -> None:
        await state.clear()
        request = SettingsUpdateRequest(
            admin_telegram_id=message.from_user.id if message.from_user else 0,
            key="is_maintenance_mode",
            value="true",
            confirm=True,
        )
        try:
            await services.admin.update_setting(request)
            await message.answer("✅ Maintenance mode <b>ENABLED</b>. Normal users are blocked.")
        except Exception as exc:
            await message.answer(f"❌ Failed to enable maintenance mode: {html.escape(str(exc))}")

    @router.message(Command("maintenance_off"))
    async def cmd_maintenance_off(message: Message, state: FSMContext) -> None:
        await state.clear()
        request = SettingsUpdateRequest(
            admin_telegram_id=message.from_user.id if message.from_user else 0,
            key="is_maintenance_mode",
            value="false",
            confirm=True,
        )
        try:
            await services.admin.update_setting(request)
            await message.answer("✅ Maintenance mode <b>DISABLED</b>. Normal users can use the bot.")
        except Exception as exc:
            await message.answer(f"❌ Failed to disable maintenance mode: {html.escape(str(exc))}")

    return router
