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
    """FSM states for updating user profile fields."""
    waiting_for_uni_id = State()
    waiting_for_password = State()
    waiting_for_dept = State()
    waiting_for_campus = State()
    waiting_for_section = State()

def build_my_data_router(services: ApplicationServices) -> Router:
    """Builds and registers all profile viewing and modification commands."""
    router = Router()

    @router.callback_query(F.data == "my_data")
    async def cb_my_data(callback_query: CallbackQuery, state: FSMContext) -> None:
        await callback_query.answer()
        if callback_query.from_user:
            import asyncio
            asyncio.create_task(services.lifecycle.bump_last_used(callback_query.from_user.id))
        await show_my_data_logic(callback_query.message, services, user_id=callback_query.from_user.id)

    @router.message(Command("my_data"))
    async def cmd_my_data(message: Message, state: FSMContext) -> None:
        if message.from_user:
            import asyncio
            asyncio.create_task(services.lifecycle.bump_last_used(message.from_user.id))
        await show_my_data_logic(message, services)

    @router.callback_query(F.data == "open_my_data")
    async def cb_open_my_data(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await show_my_data_logic(callback.message, services, user_id=callback.from_user.id)

    # --- Change University ID ---
    @router.callback_query(F.data == "change_uni_id")
    async def cb_change_uni_id(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.message.answer("Please enter your new <b>University ID</b> (e.g., UGR/1234/16):")
        await state.set_state(ProfileUpdateState.waiting_for_uni_id)
        await callback.answer()

    @router.message(ProfileUpdateState.waiting_for_uni_id, ~F.text.startswith("/"))
    async def process_uni_id_update(message: Message, state: FSMContext) -> None:
        new_id = message.text.strip().upper()
        success = await services.lifecycle.update_university_id(message.from_user.id, new_id)
        
        if success:
            await message.answer(f"✅ University ID updated to: <tg-spoiler>{html.escape(new_id)}</tg-spoiler>\n\n⚠️ <b>Important:</b> If your password also changed, please update it now to enable grade checking.")
        else:
            await message.answer("❌ Failed to update University ID.")
        
        await state.clear()
        await show_my_data_logic(message, services)

    # --- Change Password ---
    @router.callback_query(F.data == "change_password")
    async def cb_change_password(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.message.answer("Please enter your new <b>Portal Password</b>:")
        await state.set_state(ProfileUpdateState.waiting_for_password)
        await callback.answer()

    @router.message(ProfileUpdateState.waiting_for_password, ~F.text.startswith("/"))
    async def process_password_update(message: Message, state: FSMContext) -> None:
        new_password = message.text
        try:
            await message.delete()
        except Exception:
            pass
        
        if not hasattr(services, 'registration') or not hasattr(services.registration, 'cipher'):
            await message.answer("❌ Encryption service not available.")
            await state.clear()
            return
            
        success, msg = await services.lifecycle.update_password(message.from_user.id, new_password, services.registration.cipher)
        await message.answer(msg)
        if success:
            await state.clear()
            await show_my_data_logic(message, services)
        else:
            # If they failed, maybe we should let them retry unless they are locked out?
            # State is not cleared if they want to retry, but if locked out they shouldn't retry.
            if "locked" in msg.lower():
                await state.clear()
                await show_my_data_logic(message, services)

    # --- Change Department ---
    @router.callback_query(F.data == "change_department")
    async def cb_change_department(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.message.answer("Please enter your <b>Department Code</b> (e.g., SITE, CIVIL, MECHANICAL):")
        await state.set_state(ProfileUpdateState.waiting_for_dept)
        await callback.answer()

    @router.message(ProfileUpdateState.waiting_for_dept, ~F.text.startswith("/"))
    async def process_dept_update(message: Message, state: FSMContext) -> None:
        new_dept = message.text.strip().upper()
        success = await services.lifecycle.update_department(message.from_user.id, new_dept)
        
        if success:
            await message.answer(f"✅ Department updated to: <code>{html.escape(new_dept)}</code>")
        else:
            await message.answer("❌ Failed to update Department.")
        
        await state.clear()
        await show_my_data_logic(message, services)

    # --- Change Campus ---
    @router.callback_query(F.data == "change_campus")
    async def cb_change_campus(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(ProfileUpdateState.waiting_for_campus)
        
        campuses = []
        if services.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            async with SqlAlchemyRepositoryUnitOfWork(services.session_factory) as uow:
                campuses = await uow.campuses.get_all()
        
        keyboard_buttons = []
        for c in campuses:
            keyboard_buttons.append([InlineKeyboardButton(text=c.full_name, callback_data=f"campus_{c.campus_id}")])
            
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        if callback.message:
            await callback.message.answer("Please select your Campus:", reply_markup=kb)
        await callback.answer()

    @router.callback_query(ProfileUpdateState.waiting_for_campus, F.data.startswith("campus_"))
    async def process_campus_update(callback: CallbackQuery, state: FSMContext) -> None:
        campus_id = callback.data.split("_", 1)[1]
        success = await services.lifecycle.update_campus(callback.from_user.id, campus_id)
        
        if success:
            if callback.message:
                await callback.message.answer(f"✅ Campus updated to: <code>{html.escape(campus_id)}</code>")
        else:
            if callback.message:
                await callback.message.answer("❌ Failed to update Campus.")
        
        await state.clear()
        if callback.message:
            await show_my_data_logic(callback.message, services, user_id=callback.from_user.id)
        await callback.answer()

    # --- Change Section ---
    @router.callback_query(F.data == "change_section")
    async def cb_change_section(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.message.answer("Please enter your <b>Section</b> (e.g., 1, 2, 3):")
        await state.set_state(ProfileUpdateState.waiting_for_section)
        await callback.answer()

    @router.message(ProfileUpdateState.waiting_for_section, ~F.text.startswith("/"))
    async def process_section_update(message: Message, state: FSMContext) -> None:
        new_section = message.text.strip()
        
        if not new_section.isdigit() and new_section.lower() != "none":
            await message.answer("❌ Invalid Section. Must be a number or 'none'.")
            return
            
        success = await services.lifecycle.update_section(message.from_user.id, new_section)
        
        if success:
            await message.answer(f"✅ Section updated to: <code>{html.escape(new_section)}</code>")
        else:
            await message.answer("❌ Failed to update Section.")
        
        await state.clear()
        await show_my_data_logic(message, services)

    return router

async def show_my_data_logic(message: Message, services: ApplicationServices, user_id: int = None) -> None:
    target_id = user_id or message.from_user.id
    
    user_obj = await services.lifecycle.get_user_profile(target_id)
    
    if not user_obj:
        if not user_id:
            await message.answer("You are not registered. Use /register to begin.")
        return

    password = await services.lifecycle.get_decrypted_password(target_id, services.registration.cipher)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆔 Change University ID", callback_data="change_uni_id")],
        [InlineKeyboardButton(text="🔄 Change Password", callback_data="change_password")],
        [InlineKeyboardButton(text="🏫 Change Department", callback_data="change_department")],
        [InlineKeyboardButton(text="🏢 Change Campus", callback_data="change_campus")],
        [InlineKeyboardButton(text="📋 Change Section", callback_data="change_section")],
        [InlineKeyboardButton(text="🎓 View Grades", callback_data="view_grades")]
    ])
    
    text = (
        f"👤 <b>Your Data</b>\n\n"
        f"University ID: <tg-spoiler>{html.escape(user_obj.university_id)}</tg-spoiler>\n"
        f"Password: <tg-spoiler>{html.escape(password or '********')}</tg-spoiler>\n"
        f"Department: <code>{html.escape(user_obj.department_id or 'Unknown')}</code>\n"
        f"Campus: <code>{html.escape(user_obj.campus or 'Unknown')}</code>\n"
        f"Section: <code>{html.escape(user_obj.section or 'Unknown')}</code>\n"
    )

    if user_id:
        try:
            await message.edit_text(text, reply_markup=kb)
        except Exception:
            await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)
