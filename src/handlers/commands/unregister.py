"""Unregister command handler."""

from __future__ import annotations

from typing import Any

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from dto.bot import AccountDeletionRequest
from services.container import ApplicationServices

def build_unregister_router(services: ApplicationServices) -> Router:
    router = Router()

    @router.message(Command("unregister"))
    async def handle_unregister_command(message: Message) -> None:
        """Prompt the user for confirmation before deleting their account."""
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚠️ Yes, delete my account", callback_data="confirm_unregister"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_unregister")
                ]
            ]
        )
        
        await message.reply(
            "⚠️ <b>Account Deletion</b>\n\n"
            "Are you sure you want to delete your account? This will permanently remove your portal credentials and all cached grades from our database.\n\n"
            "This action cannot be undone.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    @router.callback_query(F.data == "confirm_unregister")
    async def handle_confirm_unregister(callback_query: CallbackQuery) -> None:
        """Execute account deletion."""
        if callback_query.from_user is None or callback_query.message is None:
            return

        request = AccountDeletionRequest(telegram_id=callback_query.from_user.id, confirm=True)
        result = await services.lifecycle.request_deletion(request)
        
        await callback_query.message.edit_text(result.message)
        await callback_query.answer()

    @router.callback_query(F.data == "cancel_unregister")
    async def handle_cancel_unregister(callback_query: CallbackQuery) -> None:
        """Cancel account deletion."""
        if callback_query.message is None:
            return
        await callback_query.message.edit_text("Account deletion cancelled. Your data is safe.")
        await callback_query.answer()

    return router
