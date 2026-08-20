"""Grade reading handlers with year/semester drilldown."""

from __future__ import annotations
import asyncio
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from dto.bot import GradeReadRequest
from services.container import ApplicationServices


def build_year_keyboard() -> InlineKeyboardMarkup:
    """Builds the inline keyboard for selecting an academic year."""
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
                InlineKeyboardButton(text="All Years", callback_data="grade_y:All Years")
            ]
        ]
    )

def build_semester_keyboard(year: str) -> InlineKeyboardMarkup:
    """Builds the inline keyboard for selecting a semester."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Semester One", callback_data=f"grade_s:{year}:One"),
                InlineKeyboardButton(text="Semester Two", callback_data=f"grade_s:{year}:Two")
            ],
            [
                InlineKeyboardButton(text="All Semesters", callback_data=f"grade_s:{year}:All")
            ],
            [
                InlineKeyboardButton(text="⬅️ Back", callback_data="grade_back_y")
            ]
        ]
    )

def build_grades_keyboard(year: str, semester: str, report: Any | None = None, current_page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Builds the pagination and assessment drilldown keyboard for a grade report."""
    buttons = []

    if report is not None:
        for idx, cg in enumerate(getattr(report, "course_grades", [])):
            buttons.append([
                InlineKeyboardButton(
                    text=f"📊 {cg.course_code}",
                    callback_data=f"grade_c:{year}:{semester}:{idx}"
                )
            ])

    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"grade_p:{year}:{semester}:{current_page-1}"))
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"grade_p:{year}:{semester}:{current_page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([
        InlineKeyboardButton(text="🔄 Force Refresh", callback_data=f"grade_r:{year}:{semester}")
    ])
    buttons.append([
        InlineKeyboardButton(text="📅 Filter by Year/Semester", callback_data="view_grades_filter")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_grades_router(services: ApplicationServices) -> Router:
    """Builds and registers all grade-viewing commands and interactive callbacks."""
    router = Router()

    @router.message(Command("grades"))
    async def grades(message: Message, state: FSMContext) -> None:
        await state.clear()
        user_id = message.from_user.id
        if message.from_user:
            asyncio.create_task(services.lifecycle.bump_last_used(user_id))
        
        request = GradeReadRequest(telegram_id=user_id, page_index=0)
        try:
            result = await services.grades.read(request)
            if result.message and result.message.startswith("You need to"):
                await message.answer(result.message)
            elif not result.message or result.message.startswith("No grades"):
                kb = build_grades_keyboard("All", "All", None)
                await message.answer("No grades found.", reply_markup=kb)
            else:
                kb = build_grades_keyboard("All", "All", result.report, result.current_page, result.total_pages)
                await message.answer(result.message, reply_markup=kb)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Error reading grades: {exc}", exc_info=True)
            await message.answer("❌ An error occurred while retrieving your grades. Please try again later.")

    @router.callback_query(F.data == "view_grades")
    async def view_grades_callback(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        user_id = query.from_user.id
        if query.from_user:
            asyncio.create_task(services.lifecycle.bump_last_used(user_id))
            
        request = GradeReadRequest(telegram_id=user_id, page_index=0)
        if query.message:
            await query.message.edit_text("⏳ Fetching your latest grades...")
            
        try:
            result = await services.grades.read(request)
            if result.message and result.message.startswith("You need to"):
                if query.message:
                    await query.message.edit_text(result.message)
            elif not result.message or result.message.startswith("No grades"):
                kb = build_grades_keyboard("All", "All", None)
                if query.message:
                    await query.message.edit_text("No grades found.", reply_markup=kb)
            else:
                kb = build_grades_keyboard("All", "All", result.report, result.current_page, result.total_pages)
                if query.message:
                    await query.message.edit_text(result.message, reply_markup=kb)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Error reading grades: {exc}", exc_info=True)
            if query.message:
                await query.message.edit_text("❌ An error occurred while retrieving your grades. Please try again later.")
        await query.answer()

    @router.callback_query(F.data == "view_grades_filter")
    async def view_grades_filter_callback(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        kb = build_year_keyboard()
        if query.message:
            await query.message.edit_text("Select the <b>Academic Year</b> you want to check:", reply_markup=kb)
        await query.answer()

    @router.callback_query(F.data == "grade_back_y")
    async def grade_back_y(query: CallbackQuery) -> None:
        kb = build_year_keyboard()
        if query.message:
            await query.message.edit_text("Select the <b>Academic Year</b> you want to check:", reply_markup=kb)
        await query.answer()

    @router.callback_query(F.data.startswith("grade_y:"))
    async def select_year(query: CallbackQuery) -> None:
        year = query.data.split(":")[1]
        kb = build_semester_keyboard(year)
        if query.message:
            await query.message.edit_text(f"Selected: <b>{year}</b>\nNow select the <b>Semester</b>:", reply_markup=kb)
        await query.answer()

    @router.callback_query(F.data.startswith("grade_s:"))
    async def select_semester(query: CallbackQuery) -> None:
        parts = query.data.split(":")
        year = parts[1]
        semester = parts[2]
        
        user_id = query.from_user.id
        request = GradeReadRequest(telegram_id=user_id, year_filter=year, semester_filter=semester, page_index=0)
        
        if query.message:
            await query.message.edit_text(f"⏳ Fetching grades for {year}, Semester {semester}...")
            
        try:
            result = await services.grades.read(request)
            if result.message and result.message.startswith("You need to"):
                await query.message.edit_text(result.message)
            elif not result.message or result.message.startswith("No grades"):
                kb = build_grades_keyboard(year, semester, None)
                await query.message.edit_text("No grades found for this selection.", reply_markup=kb)
            else:
                kb = build_grades_keyboard(year, semester, result.report, result.current_page, result.total_pages)
                await query.message.edit_text(result.message, reply_markup=kb)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Error reading grades: {exc}", exc_info=True)
            if query.message:
                await query.message.edit_text("❌ An error occurred while retrieving your grades. Please try again later.")
        await query.answer()

    @router.callback_query(F.data.startswith("grade_p:"))
    async def paginate_grades(query: CallbackQuery) -> None:
        parts = query.data.split(":")
        year = parts[1]
        semester = parts[2]
        page_index = int(parts[3])
        
        user_id = query.from_user.id
        request = GradeReadRequest(telegram_id=user_id, year_filter=year, semester_filter=semester, page_index=page_index)
        
        await query.answer()
        
        try:
            result = await services.grades.read(request)
            kb = build_grades_keyboard(year, semester, result.report, result.current_page, result.total_pages)
            if query.message:
                await query.message.edit_text(result.message, reply_markup=kb)
        except Exception:
            if query.message:
                await query.message.edit_text("Failed to load page.")

    @router.callback_query(F.data.startswith("grade_c:"))
    async def course_details_callback(query: CallbackQuery) -> None:
        parts = query.data.split(":")
        if len(parts) != 4:
            await query.answer("Invalid callback data", show_alert=True)
            return
            
        year = parts[1]
        semester = parts[2]
        try:
            course_idx = int(parts[3])
        except ValueError:
            await query.answer("Invalid course", show_alert=True)
            return

        user_id = query.from_user.id
        request = GradeReadRequest(telegram_id=user_id, year_filter=year, semester_filter=semester, page_index=0)
        
        await query.answer()
        
        try:
            result = await services.grades.read(request)
            if result.report and course_idx < len(result.report.course_grades):
                cg = result.report.course_grades[course_idx]
                
                assessment_text = "No assessment details available."
                if hasattr(cg, "assessment") and cg.assessment:
                    try:
                        if query.message:
                            await query.message.edit_text("⏳ Fetching assessment details...")
                        assessment_text = await services.grades.read_assessment(user_id, cg.course_code, cg.assessment)
                    except Exception as e:
                        assessment_text = f"Failed to fetch details: {e}"

                details = (
                    f"📚 <b>{cg.course_code} - {cg.course_name}</b>\n"
                    f"Credits: {cg.credit_hours} | ECTS: {cg.ects}\n"
                    f"Grade: <code>{cg.grade}</code>\n\n"
                    f"<b>Assessment Details:</b>\n{assessment_text}\n"
                )
                
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="⬅️ Back to Grades", callback_data=f"grade_p:{year}:{semester}:0")
                ]])
                
                if query.message:
                    await query.message.edit_text(details, reply_markup=kb)
            else:
                if query.message:
                    await query.message.edit_text("Course not found.")
        except Exception:
            if query.message:
                await query.message.edit_text("Failed to load course details.")

    @router.callback_query(F.data.startswith("grade_r:"))
    async def refresh_callback(query: CallbackQuery) -> None:
        if not query.message:
            return
        parts = query.data.split(":")
        year = parts[1]
        semester = parts[2]
        
        user_id = query.from_user.id
        request = GradeReadRequest(telegram_id=user_id, force_refresh=True, year_filter=year, semester_filter=semester, page_index=0)
        
        await query.answer("Scraping portal...")
        await query.message.edit_text(f"🔄 Force refreshing grades for {year}, Semester {semester}... Please wait.")
        
        try:
            result = await services.grades.read(request)
            kb = build_grades_keyboard(year, semester, result.report, result.current_page, result.total_pages)
            await query.message.edit_text(result.message, reply_markup=kb)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Error reading grades: {exc}", exc_info=True)
            await query.message.edit_text("❌ An error occurred while retrieving your grades. Please try again later.")

    return router
