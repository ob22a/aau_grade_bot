"""Grade reading handlers with year/semester pagination."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from dto.bot import GradeReadRequest
from services.container import ApplicationServices


def build_grades_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    nav_row = []

    if current_page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Prev Term", callback_data=f"grade_page:{current_page - 1}")
        )

    nav_row.append(
        InlineKeyboardButton(
            text=f"Term {current_page + 1}/{max(1, total_pages)}", callback_data="grade_noop"
        )
    )

    if current_page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(text="Next Term ➡️", callback_data=f"grade_page:{current_page + 1}")
        )

    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="🔄 Refresh Grades", callback_data="grade_refresh")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_grades_router(services: ApplicationServices) -> Router:
    router = Router()

    @router.message(Command("grades"))
    async def grades(message: Message, state: FSMContext) -> None:
        await state.clear()
        user_id = message.from_user.id if message.from_user else 0
        request = GradeReadRequest(telegram_id=user_id, page_index=0)
        try:
            result = await services.grades.read(request)
            keyboard = build_grades_keyboard(result.current_page, result.total_pages)
            await message.answer(result.message, parse_mode="Markdown", reply_markup=keyboard)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Error reading grades: {exc}", exc_info=True)
            await message.answer("❌ An error occurred while retrieving your grades. Please try again later.")

    @router.callback_query(F.data == "view_grades")
    async def view_grades_callback(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        user_id = query.from_user.id if query.from_user else 0
        request = GradeReadRequest(telegram_id=user_id, page_index=0)
        try:
            result = await services.grades.read(request)
            keyboard = build_grades_keyboard(result.current_page, result.total_pages)
            if query.message:
                await query.message.answer(result.message, parse_mode="Markdown", reply_markup=keyboard)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Error reading grades: {exc}", exc_info=True)
            if query.message:
                await query.message.answer("❌ An error occurred while retrieving your grades. Please try again later.")
        await query.answer()

    @router.callback_query(F.data.startswith("grade_page:"))
    async def page_callback(query: CallbackQuery) -> None:
        if not query.data or not query.message:
            return
        user_id = query.from_user.id if query.from_user else 0
        page_str = query.data.split(":", 1)[1]
        try:
            page_index = int(page_str)
        except ValueError:
            page_index = 0

        request = GradeReadRequest(telegram_id=user_id, page_index=page_index)
        result = await services.grades.read(request)
        keyboard = build_grades_keyboard(result.current_page, result.total_pages)
        await query.message.edit_text(result.message, parse_mode="Markdown", reply_markup=keyboard)
        await query.answer()

    @router.callback_query(F.data == "grade_refresh")
    async def refresh_callback(query: CallbackQuery) -> None:
        if not query.message:
            return
        user_id = query.from_user.id if query.from_user else 0
        request = GradeReadRequest(telegram_id=user_id, force_refresh=True, page_index=0)
        result = await services.grades.read(request)
        keyboard = build_grades_keyboard(result.current_page, result.total_pages)
        await query.message.edit_text(result.message, parse_mode="Markdown", reply_markup=keyboard)
        await query.answer("Grades refreshed!")

    @router.callback_query(F.data == "grade_noop")
    async def noop_callback(query: CallbackQuery) -> None:
        await query.answer()

    return router
