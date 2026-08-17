import html
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.container import ApplicationServices
from config import Settings

logger = logging.getLogger(__name__)

class ProfileUpdateState(StatesGroup):
    waiting_for_uni_id = State()
    waiting_for_password = State()
    waiting_for_dept = State()

def build_my_data_router(services: ApplicationServices) -> Router:
    router = Router()

    @router.callback_query(F.data == "my_data")
    async def cb_my_data(callback_query: CallbackQuery, state: FSMContext) -> None:
        await callback_query.answer()
        await cmd_my_data(callback_query.message, state, callback_query.from_user.id)

    @router.message(Command("my_data"))
    async def cmd_my_data(message: Message, state: FSMContext, user_id: int = None) -> None:
        target_id = user_id or message.from_user.id
        
        # We need to fetch the user to get their details
        import asyncio
        from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
        
        user_obj = None
        if services.account_lifecycle.session_factory is not None:
            async with SqlAlchemyRepositoryUnitOfWork(services.account_lifecycle.session_factory) as uow:
                user_obj = await uow.users.get_by_telegram_id(target_id)
        
        if not user_obj:
            if not user_id:
                await message.answer("You are not registered. Use /register to begin.")
            return

        password = await services.account_lifecycle.get_decrypted_password(target_id, services.registration.cipher)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🆔 Change University ID", callback_data="change_uni_id")],
            [InlineKeyboardButton(text="🔄 Change Password", callback_data="change_password")],
            [InlineKeyboardButton(text="🏫 Change Department", callback_data="change_department")]
        ])
        
        text = (
            f"👤 <b>Your Data</b>\n\n"
            f"University ID: <tg-spoiler>{html.escape(user_obj.university_id)}</tg-spoiler>\n"
            f"Password: <tg-spoiler>{html.escape(password or '********')}</tg-spoiler>\n"
            f"Department: <code>{html.escape(user_obj.department_id or 'Unknown')}</code>\n"
        )

        if user_id:
            try:
                await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await message.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")

    @router.callback_query(F.data == "open_my_data")
    async def cb_open_my_data(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await cmd_my_data(callback.message, state, user_id=callback.from_user.id)

    @router.callback_query(F.data == "change_uni_id")
    async def cb_change_uni_id(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.message.answer("Please enter your new <b>University ID</b> (e.g., UGR/1234/16):", parse_mode="HTML")
        await state.set_state(ProfileUpdateState.waiting_for_uni_id)
        await callback.answer()

    @router.message(ProfileUpdateState.waiting_for_uni_id, ~F.text.startswith("/"))
    async def process_uni_id_update(message: Message, state: FSMContext) -> None:
        new_id = message.text.strip().upper()
        success = await services.account_lifecycle.update_university_id(message.from_user.id, new_id)
        
        if success:
            await message.answer(f"✅ University ID updated to: <tg-spoiler>{html.escape(new_id)}</tg-spoiler>\n\n⚠️ <b>Important:</b> If your password also changed, please update it now to enable grade checking.", parse_mode="HTML")
        else:
            await message.answer("❌ Failed to update University ID.")
        
        await state.clear()
        await cmd_my_data(message, state)

    @router.callback_query(F.data == "change_password")
    async def cb_change_password(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.message.answer("Please enter your new <b>Portal Password</b>:", parse_mode="HTML")
        await state.set_state(ProfileUpdateState.waiting_for_password)
        await callback.answer()

    @router.message(ProfileUpdateState.waiting_for_password, ~F.text.startswith("/"))
    async def process_password_update(message: Message, state: FSMContext) -> None:
        new_password = message.text
        try:
            await message.delete()
        except Exception:
            logger.warning("Could not delete password message")
            
        success = await services.account_lifecycle.update_password(message.from_user.id, new_password, services.registration.cipher)
        
        if success:
            await message.answer("✅ <b>Password updated!</b>", parse_mode="HTML")
        else:
            await message.answer("❌ Failed to update Password.")
        
        await state.clear()
        await cmd_my_data(message, state)

    @router.callback_query(F.data == "change_department")
    async def cb_change_department(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.message.answer(
            "Please enter your <b>Department Code</b> (e.g., SITE, CIVIL, MECHANICAL):",
            parse_mode="HTML"
        )
        await state.set_state(ProfileUpdateState.waiting_for_dept)
        await callback.answer()

    @router.message(ProfileUpdateState.waiting_for_dept, ~F.text.startswith("/"))
    async def process_dept_update(message: Message, state: FSMContext) -> None:
        new_dept = message.text.strip().upper()
        success = await services.account_lifecycle.update_department(message.from_user.id, new_dept)
        
        if success:
            await message.answer(f"✅ Department updated to: <code>{html.escape(new_dept)}</code>", parse_mode="HTML")
        else:
            await message.answer("❌ Failed to update Department.")
        
        await state.clear()
        await cmd_my_data(message, state)

    return router
