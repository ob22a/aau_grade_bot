"""Admin command handlers."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from dto.bot import BroadcastRequest, SettingsUpdateRequest
from fsm.states import AdminBroadcastFSM
from services.container import ApplicationServices


def build_admin_router(services: ApplicationServices) -> Router:
    router = Router()

    @router.message(Command("broadcast"))
    async def begin_broadcast(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(AdminBroadcastFSM.message)
        await message.answer("Send the broadcast text.\n\n*(Send /cancel to abort)*", parse_mode="Markdown")

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

    return router
