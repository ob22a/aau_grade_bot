"""Fallback handlers for unknown commands and chat messages."""

from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from services.container import ApplicationServices


def build_fallback_router(services: ApplicationServices) -> Router:
    router = Router()

    @router.message()
    async def fallback(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Unknown command or message. Try /register, /grades, or /start.")

    from aiogram.types import CallbackQuery
    @router.callback_query()
    async def fallback_callback(callback: CallbackQuery) -> None:
        await callback.answer(
            "This button is outdated. The bot has been upgraded! Please send /start to open the new menu.",
            show_alert=True
        )
        try:
            await callback.message.delete()
        except Exception:
            pass

    return router
