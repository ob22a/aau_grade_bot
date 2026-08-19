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
    router = Router()
    router.message.filter(AdminFilter(settings.admins_telegram_id))

    @router.message(Command("broadcast"))
    async def begin_broadcast(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(AdminBroadcastFSM.message)
        await message.answer("Send the broadcast text.\n\n<i>(Send /cancel to abort)</i>", parse_mode="HTML")

    @router.message(AdminBroadcastFSM.message)
    async def capture_broadcast(message: Message, state: FSMContext) -> None:
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
            await message.answer(f"❌ Broadcast failed: {exc}")

    @router.message(Command("metrics"))
    async def metrics(message: Message, state: FSMContext) -> None:
        await state.clear()
        try:
            snapshot = await services.admin.metrics_snapshot()
            await message.answer(
                f"Uptime: {snapshot.uptime_seconds}s\nScrapes: {snapshot.scrape_attempts}\nFailures: {snapshot.scrape_failures}"
            )
        except Exception as exc:
            await message.answer(f"❌ Failed to fetch metrics: {exc}")

    @router.message(Command("setsetting"))
    async def set_setting(message: Message, state: FSMContext) -> None:
        await state.clear()
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Usage: /setsetting <key> <value>")
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
            await message.answer(f"❌ Failed to update setting: {exc}")

    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext) -> None:
        await state.clear()
        try:
            # We can check the DB for the setting if needed, but for now we'll just show the menu.
            await message.answer(
                f"🛠 <b>Admin Dashboard</b>\n\n"
                "Commands:\n"
                "/setsetting <key> <value> - Update a setting\n"
                "/metrics - View bot metrics\n"
                "/broadcast - Send a broadcast message\n"
                "/start_service - Enable grade checking service\n"
                "/stop_service - Disable grade checking service",
                parse_mode="HTML"
            )
        except Exception as exc:
            await message.answer(f"❌ Failed to load admin dashboard: {exc}")

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
            await message.answer("✅ Grade checking service <b>ENABLED</b>.", parse_mode="HTML")
        except Exception as exc:
            await message.answer(f"❌ Failed to enable service: {exc}")

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
            await message.answer("🛑 Grade checking service <b>DISABLED</b>.", parse_mode="HTML")
        except Exception as exc:
            await message.answer(f"❌ Failed to disable service: {exc}")

    return router
