"""Registration conversation handlers with validation and error handling."""

from __future__ import annotations

import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

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

    @router.message(Command("register"))
    async def begin_registration(message: Message, state: FSMContext) -> None:
        """Start registration flow, clearing any existing state."""
        await state.clear()
        await state.set_state(RegistrationFSM.university_id)
        await message.answer(
            "Send your AAU university ID in the format UGR/NNNN/YY (e.g., UGR/1234/16).\n\n"
            "*(Send /cancel at any time to abort)*",
            parse_mode="Markdown",
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
                "❌ *Invalid AAU Student ID format.*\n"
                "Expected format: `UGR/NNNN/YY` (e.g., `UGR/1234/16`).\n\n"
                "Please send a valid ID, or send /cancel to abort.",
                parse_mode="Markdown",
            )
            return

        await state.update_data(university_id=normalized_id)
        await state.set_state(RegistrationFSM.password)
        await message.answer(
            "Now send your AAU portal password.\n\n"
            "*(Send /cancel at any time to abort)*",
            parse_mode="Markdown",
        )

    @router.message(RegistrationFSM.password)
    async def capture_password(message: Message, state: FSMContext) -> None:
        """Capture password, execute registration service, and handle errors."""
        text = message.text or ""

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

        try:
            outcome = await services.registration.register(request)
            await state.clear()
            await message.answer(outcome.result.message)
        except PortalAuthenticationError:
            await state.clear()
            await message.answer(
                "❌ *Registration failed:* Invalid AAU username or password.\n"
                "Please verify your portal credentials and use /register to try again.",
                parse_mode="Markdown",
            )
        except PortalLockoutRiskError as exc:
            await state.clear()
            await message.answer(
                f"⚠️ *Registration paused for safety:*\n{exc}\n\n"
                "Please wait a few minutes and verify your password at portal.aau.edu.et before trying again.",
                parse_mode="Markdown",
            )
        except PortalTimeoutError:
            await state.clear()
            await message.answer(
                "⏳ *Connection Timeout:* The AAU portal timed out while processing your request. "
                "The portal may be slow or temporarily unresponsive. Please try again in a few minutes.",
                parse_mode="Markdown",
            )
        except PortalUnavailableError:
            await state.clear()
            await message.answer(
                "⚠️ *Portal Unavailable:* The AAU portal is currently down or unreachable. Please try again later.",
                parse_mode="Markdown",
            )
        except PortalSchemaChangedError:
            await state.clear()
            await message.answer(
                "⚠️ *Portal Layout Changed:* The AAU portal layout has changed. An administrator has been notified. Please try again later.",
                parse_mode="Markdown",
            )
        except ValueError as exc:
            await state.clear()
            await message.answer(f"❌ {exc}. Please use /register to try again.")
        except RuntimeError as exc:
            await state.clear()
            await message.answer(f"⚠️ {exc}")
        except Exception as exc:
            await state.clear()
            logger.error(f"Unexpected error during registration: {exc}", exc_info=True)
            await message.answer(
                "❌ An unexpected error occurred during registration. Please try again later."
            )

    return router
