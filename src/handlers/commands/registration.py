"""Registration conversation handlers with validation and error handling."""

from __future__ import annotations

import logging
import html
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery,InlineKeyboardMarkup, InlineKeyboardButton

from clients.aau_portal import (
    PortalAuthenticationError,
    PortalLockoutRiskError,
    PortalSchemaChangedError,
    PortalTimeoutError,
    PortalUnavailableError,
)
from utils.validation import normalize_aau_undergraduate_id
from dto.bot import RegistrationRequest
from fsm.states import RegistrationFSM
from services.container import ApplicationServices

logger = logging.getLogger(__name__)


def build_registration_router(services: ApplicationServices) -> Router:
    """Builds and registers all profile registration commands and states."""
    router = Router()

    @router.message(Command("cancel"))
    @router.message(F.text.casefold() == "cancel")
    async def cancel_registration(message: Message, state: FSMContext) -> None:
        """Cancel any active registration or stateful operation."""
        current_state = await state.get_state()
        if current_state is not None:
            await state.clear()
            await message.answer("Operation cancelled. Send /register or /grades to start.")
        else:
            await message.answer("No active operation to cancel. Send /register or /grades to start.")

    @router.callback_query(F.data == "register_start")
    async def begin_registration_callback(query: CallbackQuery, state: FSMContext) -> None:
        """Start registration flow from callback."""
        await state.clear()
        await state.set_state(RegistrationFSM.university_id)
        if query.message:
            await query.message.answer(
                "Send your AAU university ID in the format UGR/NNNN/YY (e.g., UGR/1234/16).\n\n"
                "<i>(Send /cancel at any time to abort)</i>",
            )
        await query.answer()

    @router.message(Command("register"))
    async def begin_registration(message: Message, state: FSMContext) -> None:
        """Start registration flow, clearing any existing state."""
        await state.clear()
        await state.set_state(RegistrationFSM.university_id)
        await message.answer(
            "Send your AAU university ID in the format UGR/NNNN/YY (e.g., UGR/1234/16).\n\n"
            "<i>(Send /cancel at any time to abort)</i>",
        )

    @router.message(RegistrationFSM.university_id)
    async def capture_university_id(message: Message, state: FSMContext) -> None:
        """Capture and validate student ID."""
        text = (message.text or "").strip()

        # Intercept commands sent while waiting for input
        if text.startswith("/"):
            await state.clear()
            if text.startswith("/cancel"):
                await message.answer("Registration cancelled.")
            else:
                await message.answer(
                    f"Registration cancelled because you sent '{text}'. Use /register to start over."
                )
            return

        try:
            normalized_id = normalize_aau_undergraduate_id(text)
        except ValueError:
            await message.answer(
                "❌ <b>Invalid AAU Student ID format.</b>\n"
                "Expected format: <code>UGR/NNNN/YY</code> (e.g., <code>UGR/1234/16</code>).\n\n"
                "Please send a valid ID, or send /cancel to abort.",
            )
            return
        
        await state.update_data(university_id=normalized_id)
        
        # Fetch campuses
        campuses_data = []
        if services.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            async with SqlAlchemyRepositoryUnitOfWork(services.session_factory) as uow:
                campuses = await uow.campuses.get_all()
                campuses_data = [{"id": c.campus_id, "name": c.full_name} for c in campuses]
        
        keyboard_buttons = []
        for c in campuses_data:
            keyboard_buttons.append([InlineKeyboardButton(text=c["name"], callback_data=f"campus_{c['id']}")])
            
        # Add a skip button if needed, but user wants campus input. Let's make it mandatory if available.
        if not campuses_data:
            # Fallback to section if no campuses
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Skip Section", callback_data="skip_section")]])
            await state.set_state(RegistrationFSM.section)
            await message.answer(
                "Great! Now enter your <b>Section</b> (e.g., 1,2,3):\n\n"
                "<i>(Send /cancel at any time to abort)</i>",
                reply_markup=kb
            )
            return

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await state.set_state(RegistrationFSM.campus)
        await message.answer(
            "Great! Please select your <b>Campus</b>:\n\n"
            "<i>(Send /cancel at any time to abort)</i>",
            reply_markup=kb
        )

    @router.callback_query(RegistrationFSM.campus, F.data.startswith("campus_"))
    async def capture_campus(query: CallbackQuery, state: FSMContext) -> None:
        """Capture campus selection."""
        campus_id = query.data.split("_", 1)[1]
        await state.update_data(campus=campus_id)
        await query.answer(f"Campus selected: {campus_id}")
        
        departments_data = []
        if services.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from sqlalchemy import select
            from database.models import Department
            async with SqlAlchemyRepositoryUnitOfWork(services.session_factory) as uow:
                # Fetch departments for this campus
                depts = await uow.session.scalars(select(Department).where(Department.campus_id == campus_id))
                departments_data = [{"id": d.department_id, "name": d.full_name} for d in depts]
                
        if not departments_data:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Skip Section", callback_data="skip_section")],
            ])
            await state.set_state(RegistrationFSM.section)
            if query.message:
                await query.message.answer(
                    "Now enter your <b>Section</b> (e.g., 1,2,3):\n\n"
                    "<i>(Send /cancel at any time to abort)</i>",
                    reply_markup=kb
                )
            return

        keyboard_buttons = []
        for d in departments_data:
            keyboard_buttons.append([InlineKeyboardButton(text=d["name"], callback_data=f"dept_{d['id']}")])
            
        keyboard_buttons.append([InlineKeyboardButton(text="Skip Department", callback_data="skip_department")])
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await state.set_state(RegistrationFSM.department)
        if query.message:
            await query.message.answer(
                "Great! Please select your <b>Department</b>:\n\n"
                "<i>(Send /cancel at any time to abort)</i>",
                reply_markup=kb
            )

    @router.callback_query(RegistrationFSM.department, F.data.startswith("dept_"))
    async def capture_department(query: CallbackQuery, state: FSMContext) -> None:
        """Capture department selection."""
        dept_id = query.data.split("_", 1)[1]
        await state.update_data(department_id=dept_id)
        await query.answer("Department selected.")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Skip Section", callback_data="skip_section")],
        ])
        await state.set_state(RegistrationFSM.section)
        if query.message:
            await query.message.answer(
                "Now enter your <b>Section</b> (e.g., 1,2,3):\n\n"
                "<i>(Send /cancel at any time to abort)</i>",
                reply_markup=kb
            )

    @router.callback_query(RegistrationFSM.department, F.data == "skip_department")
    async def skip_department_callback(query: CallbackQuery, state: FSMContext) -> None:
        """Skip department input and proceed to section."""
        await query.answer("Department skipped.")
        
        await state.update_data(department_id=None)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Skip Section", callback_data="skip_section")],
        ])
        await state.set_state(RegistrationFSM.section)
        if query.message:
            await query.message.answer(
                "Now enter your <b>Section</b> (e.g., 1,2,3):\n\n"
                "<i>(Send /cancel at any time to abort)</i>",
                reply_markup=kb
            )

    @router.callback_query(RegistrationFSM.section, F.data == "skip_section")
    async def skip_section_callback(query: CallbackQuery, state: FSMContext) -> None:
        """Skip section input and proceed to password."""
        await query.answer("Section input skipped. Proceeding to password entry.")
        
        await state.update_data(section=None)
        await state.set_state(RegistrationFSM.password)
        if query.message:
            await query.message.answer(
                "Now send your <b>AAU Portal Password</b>.\n\n"
                "<i>(Send /cancel at any time to abort)</i>",
            )
    

    @router.message(RegistrationFSM.section)
    async def capture_section(message: Message, state: FSMContext) -> None:
        """Capture section input and proceed to password."""
        text = (message.text or "").strip()

        # Intercept commands sent while waiting for input
        if text.startswith("/"):
            await state.clear()
            if text.startswith("/cancel"):
                await message.answer("Registration cancelled.")
            else:
                await message.answer(
                    f"Registration cancelled because you sent '{text}'. Use /register to start over."
                )
            return

        # Validate section input (should be a number)
        if not text.isdigit():
            await message.answer(
                "❌ <b>Invalid Section format.</b>\n"
                "Section should be a number (e.g., 1, 2, 3).\n\n"
                "Please send a valid section, or send /cancel to abort.",
            )
            return

        section_number = int(text)
        await state.update_data(section=section_number)
        await state.set_state(RegistrationFSM.password)
        await message.answer(
            "Now send your <b>AAU Portal Password</b>.\n\n"
            "<i>(Send /cancel at any time to abort)</i>",
        )

    @router.message(RegistrationFSM.password)
    async def capture_password(message: Message, state: FSMContext) -> None:
        """Capture password, execute registration service, and handle errors."""
        text = message.text or ""
        
        try:
            await message.delete()
        except Exception as e:
            logger.warning(f"Could not delete password message: {e}")

        # Intercept commands sent while waiting for input
        if text.startswith("/"):
            await state.clear()
            if text.startswith("/cancel"):
                await message.answer("Registration cancelled.")
            else:
                await message.answer(
                    f"Registration cancelled because you sent '{text}'. Use /register to start over."
                )
            return

        await state.update_data(password=text)
        data = await state.get_data()
        
        await state.set_state(RegistrationFSM.confirm)
        
        campus_id = data.get("campus", "Not specified")
        dept_id = data.get("department_id", "Not specified")
        section = data.get("section", "Not specified")
        
        msg = (
            "📋 <b>Registration Summary</b>\n\n"
            f"<b>University ID:</b> <code>{data.get('university_id')}</code>\n"
            f"<b>Campus:</b> {campus_id}\n"
            f"<b>Department:</b> {dept_id}\n"
            f"<b>Section:</b> {section}\n"
            f"<b>Password:</b> <tg-spoiler>{text}</tg-spoiler>\n\n"
            "Is this information correct?"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm & Register", callback_data="confirm_registration")],
            [InlineKeyboardButton(text="✏️ Edit Password", callback_data="edit_password")],
            [InlineKeyboardButton(text="✏️ Edit Section", callback_data="edit_section")],
            [InlineKeyboardButton(text="✏️ Edit Department", callback_data="edit_department")],
            [InlineKeyboardButton(text="✏️ Edit Campus", callback_data="edit_campus")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_registration")]
        ])
        
        await message.answer(msg, reply_markup=kb)

    @router.callback_query(RegistrationFSM.confirm, F.data == "cancel_registration")
    async def confirm_cancel(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        if query.message:
            await query.message.edit_text("Registration cancelled. Use /register to start over.")
        await query.answer()

    @router.callback_query(RegistrationFSM.confirm, F.data == "edit_password")
    async def confirm_edit_password(query: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(RegistrationFSM.password)
        if query.message:
            await query.message.answer("Please send your AAU Portal Password:")
        await query.answer()

    @router.callback_query(RegistrationFSM.confirm, F.data == "edit_section")
    async def confirm_edit_section(query: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(RegistrationFSM.section)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Skip Section", callback_data="skip_section")],
        ])
        if query.message:
            await query.message.answer("Please enter your Section (e.g., 1, 2, 3) or skip:", reply_markup=kb)
        await query.answer()

    @router.callback_query(RegistrationFSM.confirm, F.data == "edit_campus")
    async def confirm_edit_campus(query: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(RegistrationFSM.campus)
        
        campuses = []
        if services.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            async with SqlAlchemyRepositoryUnitOfWork(services.session_factory) as uow:
                campuses = await uow.campuses.get_all()
        
        keyboard_buttons = []
        for c in campuses:
            keyboard_buttons.append([InlineKeyboardButton(text=c.full_name, callback_data=f"campus_{c.campus_id}")])
            
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        if query.message:
            await query.message.answer("Please select your Campus:", reply_markup=kb)
        await query.answer()

    @router.callback_query(RegistrationFSM.confirm, F.data == "edit_department")
    async def confirm_edit_department(query: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        campus_id = data.get("campus")
        
        departments_data = []
        if services.session_factory is not None and campus_id:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from sqlalchemy import select
            from database.models import Department
            async with SqlAlchemyRepositoryUnitOfWork(services.session_factory) as uow:
                depts = await uow.session.scalars(select(Department).where(Department.campus_id == campus_id))
                departments_data = [{"id": d.department_id, "name": d.full_name} for d in depts]
                
        keyboard_buttons = []
        for d in departments_data:
            keyboard_buttons.append([InlineKeyboardButton(text=d["name"], callback_data=f"dept_{d['id']}")])
        keyboard_buttons.append([InlineKeyboardButton(text="Skip Department", callback_data="skip_department")])
        
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await state.set_state(RegistrationFSM.department)
        if query.message:
            await query.message.answer("Please select your Department:", reply_markup=kb)
        await query.answer()

    @router.callback_query(RegistrationFSM.confirm, F.data == "confirm_registration")
    async def confirm_register(query: CallbackQuery, state: FSMContext) -> None:
        try:
            await query.answer()
        except Exception:
            pass
            
        data = await state.get_data()
        
        request = RegistrationRequest(
            telegram_id=query.from_user.id,
            university_id=data.get("university_id", ""),
            password=data.get("password", ""),
            campus=data.get("campus"),
            department_id=data.get("department_id"),
            section=str(data.get("section")) if data.get("section") is not None else None,
        )

        if query.message:
            await query.message.edit_text("⏳ <b>Authenticating with AAU portal... Please wait.</b>")
            
        try:
            outcome = await services.registration.register(request)
            await state.clear()
            if query.message:
                await query.message.answer(outcome.result.message)
                from handlers.commands.my_data import show_my_data_logic
                await show_my_data_logic(query.message, services, user_id=query.from_user.id)
        except PortalAuthenticationError:
            await state.clear()
            if query.message:
                await query.message.answer(
                    "❌ <b>Registration failed:</b> Invalid AAU username or password.\n"
                    "Please verify your portal credentials and use /register to try again.",
                )
        except PortalLockoutRiskError as exc:
            await state.clear()
            if query.message:
                await query.message.answer(
                    f"⚠️ <b>Registration paused for safety:</b>\n{exc}\n\n"
                    "Please wait a few minutes and verify your password at portal.aau.edu.et before trying again.",
                )
        except PortalTimeoutError:
            await state.clear()
            if query.message:
                await query.message.answer(
                    "⏳ <b>Connection Timeout:</b> The AAU portal timed out while processing your request. "
                    "The portal may be slow or temporarily unresponsive. Please try again in a few minutes.",
                )
        except PortalUnavailableError:
            await state.clear()
            if query.message:
                await query.message.answer(
                    "⚠️ <b>Portal Unavailable:</b> The AAU portal is currently down or unreachable. Please try again later.",
                )
        except PortalSchemaChangedError as exc:
            await state.clear()
            
            # Extract HTML snippet if available
            html_snippet = exc.diagnostic.html_snippet if exc.diagnostic and hasattr(exc.diagnostic, "html_snippet") and exc.diagnostic.html_snippet else "N/A"
            escaped_snippet = html.escape(html_snippet)
            admin_msg = (
                f"🚨 <b>PORTAL SCHEMA CHANGED</b> 🚨\n\n"
                f"A schema change was detected during registration for user <code>{query.from_user.id if query.from_user else 'Unknown'}</code>.\n"
                f"<b>Error:</b> {exc}\n\n"
                f"<b>HTML Snippet:</b>\n<pre><code class='language-html'>{escaped_snippet}</code></pre>"
            )
            # Send message to all admins using notification service
            if hasattr(services, 'notification') and hasattr(services.notification, 'send_admin'):
                await services.notification.send_admin(admin_msg)
            else:
                logger.error("Notification service not found, cannot alert admin.")

            if query.message:
                await query.message.answer(
                    "⚠️ <b>Portal Layout Changed:</b> The AAU portal layout has changed. An administrator has been notified. Please try again later.",
                )
        except ValueError as exc:
            await state.clear()
            if query.message:
                await query.message.answer(f"❌ {exc}. Please use /register to try again.")
        except RuntimeError as exc:
            await state.clear()
            if query.message:
                await query.message.answer(f"⚠️ {exc}")
        except Exception as exc:
            await state.clear()
            logger.error("Unexpected error during registration", exc_info=exc)
            if query.message:
                await query.message.answer("⚠️ An unexpected error occurred. Please try again later.")

    return router
