"""Start command router."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from services.container import ApplicationServices


def build_start_router(services: ApplicationServices) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Welcome to AAU Grade Bot. Use /register to connect your account or /grades to view cached grades."
        )

    return router
