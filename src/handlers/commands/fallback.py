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

    return router
