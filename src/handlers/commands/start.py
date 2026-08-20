"""Start command router."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from services.container import ApplicationServices

from config import Settings

def build_start_router(settings: Settings, services: ApplicationServices) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        
        is_registered = False
        is_admin = False
        if message.from_user:
            is_registered = await services.lifecycle.is_registered(message.from_user.id)
            admins = settings.admins_telegram_id or []
            if message.from_user.id in admins:
                is_admin = True
            
        if is_registered:
            buttons = [
                [
                    InlineKeyboardButton(text="👤 My Data", callback_data="my_data"),
                    InlineKeyboardButton(text="📊 View Grades", callback_data="view_grades")
                ]
            ]
        else:
            buttons = [
                [InlineKeyboardButton(text="🔐 Register", callback_data="register_start")]
            ]
            
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_text = (
            "👋 Welcome! I am your <b>AAU Grade Bot</b>.\n\n"
            "🔒 <b>Privacy First</b>: All your grades and portal data are secured with military-grade <b>AES-256 encryption</b>. Only you can view your results.\n\n"
            "Use the buttons below to get started."
        )
        if is_admin:
            msg_text += "\n\n🛠 <b>Admin</b>: You have admin privileges! Send /admin to view your dashboard, /metrics for stats, or /broadcast to send announcements."
            
        await message.answer(msg_text, reply_markup=kb)

    return router
