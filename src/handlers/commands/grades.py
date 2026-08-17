"""Grade reading handlers with year/semester drilldown."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from dto.bot import GradeReadRequest
from services.container import ApplicationServices


def build_year_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Year 1", callback_data="grade_y:Year 1"),
                InlineKeyboardButton(text="Year 2", callback_data="grade_y:Year 2")
            ],
            [
                InlineKeyboardButton(text="Year 3", callback_data="grade_y:Year 3"),
                InlineKeyboardButton(text="Year 4", callback_data="grade_y:Year 4")
            ],
            [
                InlineKeyboardButton(text="Year 5", callback_data="grade_y:Year 5"),
                InlineKeyboardButton(text="Year 6", callback_data="grade_y:Year 6")
            ],
            [
                InlineKeyboardButton(text="✨ All Years", callback_data="grade_y:All")
            ]
        ]
    )

def build_semester_keyboard(year: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Semester One", callback_data=f"grade_s:{year}:One"),
                InlineKeyboardButton(text="Semester Two", callback_data=f"grade_s:{year}:Two")
            ],
            [
                InlineKeyboardButton(text="✨ All Semesters", callback_data=f"grade_s:{year}:All")
            ],
            [
                InlineKeyboardButton(text="⬅️ Back", callback_data="grade_back_y")
            ]
        ]
    )

def build_grades_keyboard(year: str, semester: str, current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    nav_row = []

    if current_page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Prev", callback_data=f"grade_p:{year}:{semester}:{current_page - 1}")
        )

    nav_row.append(
        InlineKeyboardButton(
            text=f"Page {current_page + 1}/{max(1, total_pages)}", callback_data="grade_noop"
        )
    )

    if current_page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(text="Next ➡️", callback_data=f"grade_p:{year}:{semester}:{current_page + 1}")
        )

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="🔄 Force Refresh", callback_data=f"grade_r:{year}:{semester}")
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Back", callback_data=f"grade_y:{year}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_grades_router(services: ApplicationServices) -> Router:
    router = Router()

    @router.message(Command("grades"))
    async def grades(message: Message, state: FSMContext) -> None:
        await state.clear()
        kb = build_year_keyboard()
        await message.answer("Select the <b>Academic Year</b> you want to check:", reply_markup=kb, parse_mode="HTML")

    @router.callback_query(F.data == "view_grades")
    async def view_grades_callback(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        kb = build_year_keyboard()
        if query.message:
            await query.message.answer("Select the <b>Academic Year</b> you want to check:", reply_markup=kb, parse_mode="HTML")
        await query.answer()

    @router.callback_query(F.data == "grade_back_y")
    async def grade_back_y(query: CallbackQuery) -> None:
        kb = build_year_keyboard()
        if query.message:
            await query.message.edit_text("Select the <b>Academic Year</b> you want to check:", reply_markup=kb, parse_mode="HTML")
        await query.answer()

    @router.callback_query(F.data.startswith("grade_y:"))
    async def select_year(query: CallbackQuery) -> None:
        year = query.data.split(":")[1]
        kb = build_semester_keyboard(year)
        if query.message:
            await query.message.edit_text(f"Selected: <b>{year}</b>\nNow select the <b>Semester</b>:", reply_markup=kb, parse_mode="HTML")
        await query.answer()

    @router.callback_query(F.data.startswith("grade_s:"))
    async def select_semester(query: CallbackQuery) -> None:
        parts = query.data.split(":")
        year = parts[1]
        semester = parts[2]
        
        user_id = query.from_user.id
        request = GradeReadRequest(telegram_id=user_id, year_filter=year, semester_filter=semester, page_index=0)
        
        if query.message:
            await query.message.edit_text(f"⏳ Fetching grades for {year}, Semester {semester}...", parse_mode="HTML")
            
        try:
            result = await services.grades.read(request)
            if not result.message:
                kb = build_grades_keyboard(year, semester, 0, 0)
                await query.message.edit_text("No grades found for this selection.", reply_markup=kb)
            else:
                kb = build_grades_keyboard(year, semester, result.current_page, result.total_pages)
                await query.message.edit_text(result.message, parse_mode="Markdown", reply_markup=kb)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Error reading grades: {exc}", exc_info=True)
            if query.message:
                await query.message.edit_text("❌ An error occurred while retrieving your grades. Please try again later.")
        await query.answer()

    @router.callback_query(F.data.startswith("grade_p:"))
    async def page_callback(query: CallbackQuery) -> None:
        if not query.data or not query.message:
            return
        parts = query.data.split(":")
        year = parts[1]
        semester = parts[2]
        try:
            page_index = int(parts[3])
        except ValueError:
            page_index = 0

        user_id = query.from_user.id
        request = GradeReadRequest(telegram_id=user_id, year_filter=year, semester_filter=semester, page_index=page_index)
        
        result = await services.grades.read(request)
        kb = build_grades_keyboard(year, semester, result.current_page, result.total_pages)
        await query.message.edit_text(result.message, parse_mode="Markdown", reply_markup=kb)
        await query.answer()

    @router.callback_query(F.data.startswith("grade_r:"))
    async def refresh_callback(query: CallbackQuery) -> None:
        if not query.message:
            return
        parts = query.data.split(":")
        year = parts[1]
        semester = parts[2]
        
        user_id = query.from_user.id
        request = GradeReadRequest(telegram_id=user_id, force_refresh=True, year_filter=year, semester_filter=semester, page_index=0)
        
        await query.message.edit_text(f"🔄 Force refreshing grades for {year}, Semester {semester}... Please wait.", parse_mode="HTML")
        
        try:
            result = await services.grades.read(request)
            kb = build_grades_keyboard(year, semester, result.current_page, result.total_pages)
            await query.message.edit_text(result.message, parse_mode="Markdown", reply_markup=kb)
            await query.answer("Grades refreshed!")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Error reading grades: {exc}", exc_info=True)
            await query.message.edit_text("❌ An error occurred while retrieving your grades. Please try again later.")

    @router.callback_query(F.data == "grade_noop")
    async def noop_callback(query: CallbackQuery) -> None:
        await query.answer()

    return router
