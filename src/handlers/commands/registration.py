"""Registration conversation handlers with validation and error handling."""

from __future__ import annotations

import logging
import html
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

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
                parse_mode="HTML",
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
            parse_mode="HTML",
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
                parse_mode="HTML",
            )
            return

        await state.update_data(university_id=normalized_id)
        await state.set_state(RegistrationFSM.password)
        await message.answer(
            "Great! Now enter your <b>Portal Password</b> (this will be encrypted safely):\n\n"
            "<i>(Send /cancel at any time to abort)</i>",
            parse_mode="HTML",
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

        data = await state.get_data()
        request = RegistrationRequest(
            telegram_id=message.from_user.id if message.from_user else 0,
            university_id=data.get("university_id", ""),
            password=text,
        )

        status_msg = await message.answer("⏳ <b>Received password!</b> Authenticating with AAU portal... Please wait.", parse_mode="HTML")
        try:
            outcome = await services.registration.register(request)
            await state.clear()
            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
            await message.answer(outcome.result.message, parse_mode="HTML")
        except PortalAuthenticationError:
            await state.clear()
            if status_msg:
                await status_msg.delete()
            await message.answer(
                "❌ <b>Registration failed:</b> Invalid AAU username or password.\n"
                "Please verify your portal credentials and use /register to try again.",
                parse_mode="HTML",
            )
        except PortalLockoutRiskError as exc:
            await state.clear()
            if status_msg:
                await status_msg.delete()
            await message.answer(
                f"⚠️ *Registration paused for safety:*\n{exc}\n\n"
                "Please wait a few minutes and verify your password at portal.aau.edu.et before trying again.",
                parse_mode="Markdown",
            )
        except PortalTimeoutError:
            await state.clear()
            await status_msg.delete()
            await message.answer(
                "⏳ *Connection Timeout:* The AAU portal timed out while processing your request. "
                "The portal may be slow or temporarily unresponsive. Please try again in a few minutes.",
                parse_mode="Markdown",
            )
        except PortalUnavailableError:
            await state.clear()
            await status_msg.delete()
            await message.answer(
                "⚠️ *Portal Unavailable:* The AAU portal is currently down or unreachable. Please try again later.",
                parse_mode="Markdown",
            )
        except PortalSchemaChangedError as exc:
            await state.clear()
            await status_msg.delete()
            
            # Extract HTML snippet if available
            html_snippet = exc.diagnostic.html_snippet if exc.diagnostic and hasattr(exc.diagnostic, "html_snippet") and exc.diagnostic.html_snippet else "N/A"
            escaped_snippet = html.escape(html_snippet)
            admin_msg = (
                f"🚨 <b>PORTAL SCHEMA CHANGED</b> 🚨\n\n"
                f"A schema change was detected during registration for user <code>{message.from_user.id if message.from_user else 'Unknown'}</code>.\n"
                f"<b>Error:</b> {exc}\n\n"
                f"<b>HTML Snippet:</b>\n<pre><code class='language-html'>{escaped_snippet}</code></pre>"
            )
            # Send message to all admins using notification service
            if hasattr(services, 'notification') and hasattr(services.notification, 'send_admin'):
                await services.notification.send_admin(admin_msg)
            else:
                logger.error("Notification service not found, cannot alert admin.")

            await message.answer(
                "⚠️ *Portal Layout Changed:* The AAU portal layout has changed. An administrator has been notified. Please try again later.",
                parse_mode="Markdown",
            )
        except ValueError as exc:
            await state.clear()
            await status_msg.delete()
            await message.answer(f"❌ {exc}. Please use /register to try again.")
        except RuntimeError as exc:
            await state.clear()
            await status_msg.delete()
            await message.answer(f"⚠️ {exc}")
        except Exception as exc:
            await state.clear()
            await status_msg.delete()
            logger.error("Unexpected error during registration", exc_info=exc)
            await message.answer("⚠️ An unexpected error occurred. Please try again later.")

    return router
