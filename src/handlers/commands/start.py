"""Start command router."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from services.container import ApplicationServices

def build_start_router(services: ApplicationServices) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        
        is_registered = False
        if message.from_user:
            is_registered = await services.lifecycle.is_registered(message.from_user.id)
            
        if is_registered:
            buttons = [
                InlineKeyboardButton(text="👤 My Data", callback_data="my_data"),
                InlineKeyboardButton(text="📊 View Grades", callback_data="view_grades")
            ]
        else:
            buttons = [
                InlineKeyboardButton(text="🔐 Register", callback_data="register_start"),
                InlineKeyboardButton(text="📊 View Grades", callback_data="view_grades")
            ]
            
        kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
        await message.answer(
            "👋 Welcome! I am your <b>AAU Grade Bot</b>.\n\n"
            "🔒 <b>Privacy First</b>: All your grades and portal data are secured with military-grade <b>AES-256 encryption</b>. Only you can view your results.\n\n"
            "Use the buttons below to get started.",
            parse_mode="HTML",
            reply_markup=kb
        )

    return router
