from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.connection import SessionLocal
from services.user_service import UserService
from sqlalchemy import select
import logging
import os
import asyncio
import html
router = Router()
logger = logging.getLogger(__name__)

class RegistrationState(StatesGroup):
    waiting_for_id = State()
    waiting_for_password = State()
    waiting_for_department = State()
    waiting_for_uni_id = State() # For updates
    waiting_for_password_update = State() # For password-only updates
    waiting_for_dept_update = State() # For department updates

class UpdateState(StatesGroup):
    waiting_for_year = State()
    waiting_for_semester = State()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    async with SessionLocal() as db:
        user_service = UserService(db)
        user = await user_service.get_user_by_telegram_id(message.from_user.id)
        
        if user:
            password = await user_service.get_decrypted_password(user)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Check Grades", callback_data="check_ALL")],
                [InlineKeyboardButton(text="⚙️ Manage My Data", callback_data="open_my_data")]
            ])
            await message.answer(
                f"👋 <b>Welcome back!</b>\n\n"
                f"Logged in as: <code>{html.escape(user.university_id)}</code>\n"
                f"Department: <code>{html.escape(user.department_id)}</code>\n"
                f"Status: <code>{html.escape(user.academic_year)}, {html.escape(user.semester)}</code>\n\n"
                "You can use the buttons below or /check_grades and /my_data commands.",
                reply_markup=kb,
                parse_mode="HTML"
            )
            return

    await message.answer(
        "👋 Welcome! I am your **AAU Grade Bot**.\n\n"
        "🔒 **Privacy First**: All your grades and portal data are secured with military-grade **AES-256 encryption**. Only you can view your results.\n\n"
        "To get started, please enter your **University ID** (e.g., UGR/1234/16):",
        parse_mode="Markdown"
    )
    await state.set_state(RegistrationState.waiting_for_id)

@router.callback_query(F.data == "open_my_data")
async def cb_open_my_data(callback: CallbackQuery):
    await callback.answer()
    # Pass the actual telegram_id from the callback
    await cmd_my_data(callback.message, user_id=callback.from_user.id)

@router.message(RegistrationState.waiting_for_id, ~F.text.startswith("/"))
async def process_id(message: Message, state: FSMContext):
    await state.update_data(id=message.text)
    await message.answer("Great! Now enter your <b>Portal Password</b> (this will be encrypted safely):", parse_mode="HTML")
    await state.set_state(RegistrationState.waiting_for_password)

@router.message(RegistrationState.waiting_for_password, ~F.text.startswith("/"))
async def process_password(message: Message, state: FSMContext):
    await state.update_data(password=message.text)
    await message.answer("Finally, enter your <b>Department Abbreviation</b> (e.g., SITE):", parse_mode="HTML")
    await state.set_state(RegistrationState.waiting_for_department)

@router.message(RegistrationState.waiting_for_department, ~F.text.startswith("/"))
async def process_department(message: Message, state: FSMContext):
    data = await state.get_data()
    uni_id = data['id']
    password = data['password']
    dept = message.text.upper()
    
    async with SessionLocal() as db:
        user_service = UserService(db)
        await user_service.register_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            university_id=uni_id,
            password=password,
            campus_id="CTBE", # Hardcoded for now per requirements
            department_id=dept
        )
        # Fetch newly created user to show full summary
        user = await user_service.get_user_by_telegram_id(message.from_user.id)
        await db.commit()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Change Year", callback_data="change_year"), InlineKeyboardButton(text="⏳ Change Semester", callback_data="change_sem")],
        [InlineKeyboardButton(text="📊 Check My Grades", callback_data="check_ALL")]
    ])

    await message.answer(
        f"✅ <b>Registration complete!</b>\n\n"
        f"University ID: <code>{user.university_id}</code>\n"
        f"Department: <code>{user.department_id}</code>\n\n"
        "⚡ <b>Initial Sync Started</b>\n"
        "I'm now fetching your historical grades from the portal for the first time. This usually takes 1-2 minutes.\n\n"
        "I'll notify you as soon as I have the results! ⏳",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    # Trigger Initial Sync in background
    from workers.tasks import run_check_user_grades
    asyncio.create_task(run_check_user_grades(message.from_user.id, "All"))
    
    await state.clear()

@router.message(Command("my_data"))
async def cmd_my_data(message: Message, user_id: int = None):
    # If user_id is passed, use it (from callback), otherwise use message.from_user.id
    target_id = user_id or message.from_user.id
    
    async with SessionLocal() as db:
        user_service = UserService(db)
        user = await user_service.get_user_by_telegram_id(target_id)
        
        if not user:
            # If called via command, use message.answer
            await message.answer("You are not registered. Use /start to begin.")
            return
            
        password = await user_service.get_decrypted_password(user)
        
        from services.audit_service import AuditService
        await AuditService(db).log("VIEW_MY_DATA", target_id)
        await db.commit()

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🆔 Change University ID", callback_data="change_uni_id")],
            [InlineKeyboardButton(text="🔄 Change Password", callback_data="change_password")],
            [InlineKeyboardButton(text="🏫 Change Department", callback_data="change_department")],
            [InlineKeyboardButton(text="📅 Change Year", callback_data="change_year"), InlineKeyboardButton(text="⏳ Change Semester", callback_data="change_sem")]
        ])
        
        text = (
            f"👤 <b>Your Data</b>\n\n"
            f"University ID: <code>{html.escape(user.university_id)}</code>\n"
            f"Password: <code>{html.escape(password or '********')}</code>\n"
            f"Department: <code>{html.escape(user.department_id)}</code>\n"
            f"Campus: <code>{html.escape(user.campus_id)}</code>\n"
            f"Academic Status: <code>{html.escape(user.academic_year)}, {html.escape(user.semester)}</code>"
        )

        # If called from a callback, message is the previous message we can edit
        if user_id:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "change_uni_id")
async def cb_change_uni_id(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Please enter your new <b>University ID</b> (e.g., UGR/1234/16):", parse_mode="HTML")
    await state.set_state(RegistrationState.waiting_for_uni_id)
    await callback.answer()

@router.message(RegistrationState.waiting_for_uni_id, ~F.text.startswith("/"))
async def process_uni_id_update(message: Message, state: FSMContext):
    new_id = message.text
    async with SessionLocal() as db:
        user_service = UserService(db)
        await user_service.update_university_id(message.from_user.id, new_id)
        await db.commit()
    
    await message.answer(f"✅ University ID updated to: <code>{html.escape(new_id)}</code>\n\nI'm triggering an update sync to verify your new ID...", parse_mode="HTML")
    
    from workers.tasks import run_check_user_grades
    asyncio.create_task(run_check_user_grades(message.from_user.id, "All"))
    
    await state.clear()
    await cmd_my_data(message)

@router.callback_query(F.data == "change_password")
async def cb_change_password(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Please enter your new <b>Portal Password</b>:", parse_mode="HTML")
    await state.set_state(RegistrationState.waiting_for_password_update)
    async with SessionLocal() as db:
        from services.audit_service import AuditService
        await AuditService(db).log("CHANGE_PASSWORD_START", callback.from_user.id)
        await db.commit()
    await callback.answer()

@router.message(RegistrationState.waiting_for_password_update, ~F.text.startswith("/"))
async def process_password_update(message: Message, state: FSMContext):
    new_password = message.text
    async with SessionLocal() as db:
        user_service = UserService(db)
        await user_service.update_password(message.from_user.id, new_password)
        await db.commit()
    
    await message.answer("✅ <b>Password updated!</b>\n\nI'm triggering an update sync to verify your new password...", parse_mode="HTML")
    
    from workers.tasks import run_check_user_grades
    asyncio.create_task(run_check_user_grades(message.from_user.id, "All"))
    
    await state.clear()
    await cmd_my_data(message)

@router.callback_query(F.data == "change_department")
async def cb_change_department(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Please enter your <b>Department Code</b> (e.g., SITE, CIVIL, MECHANICAL):",
        parse_mode="HTML"
    )
    await state.set_state(RegistrationState.waiting_for_dept_update)
    await callback.answer()

@router.message(RegistrationState.waiting_for_dept_update, ~F.text.startswith("/"))
async def process_dept_update(message: Message, state: FSMContext):
    new_dept = message.text.strip().upper()
    async with SessionLocal() as db:
        user_service = UserService(db)
        user = await user_service.get_user_by_telegram_id(message.from_user.id)
        if user:
            user.department_id = new_dept
            await db.commit()
    
    await message.answer(f"✅ Department updated to: <code>{html.escape(new_dept)}</code>", parse_mode="HTML")
    await state.clear()
    await cmd_my_data(message)

@router.callback_query(F.data == "change_year")
async def cb_change_year(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Year 1", callback_data="set_year_Year 1"), InlineKeyboardButton(text="Year 2", callback_data="set_year_Year 2")],
        [InlineKeyboardButton(text="Year 3", callback_data="set_year_Year 3"), InlineKeyboardButton(text="Year 4", callback_data="set_year_Year 4")],
        [InlineKeyboardButton(text="Year 5", callback_data="set_year_Year 5"), InlineKeyboardButton(text="Year 6", callback_data="set_year_Year 6")],
        [InlineKeyboardButton(text="Year 7", callback_data="set_year_Year 7")]
    ])
    await callback.message.answer("Select your current <b>Academic Year</b>:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "change_sem")
async def cb_change_sem(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Semester One", callback_data="set_sem_One"), InlineKeyboardButton(text="Semester Two", callback_data="set_sem_Two")]
    ])
    await callback.message.answer("Select your current <b>Semester</b>:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("set_year_"))
async def cb_set_year(callback: CallbackQuery):
    year = callback.data.replace("set_year_", "")
    async with SessionLocal() as db:
        user_service = UserService(db)
        await user_service.update_academic_status(callback.from_user.id, year=year)
        await db.commit()
    await callback.message.edit_text(f"✅ Academic Year updated to <b>{html.escape(year)}</b>.", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("set_sem_"))
async def cb_set_sem(callback: CallbackQuery):
    sem = f"Semester : {callback.data.replace('set_sem_', '')}"
    async with SessionLocal() as db:
        user_service = UserService(db)
        await user_service.update_academic_status(callback.from_user.id, semester=sem)
        await db.commit()
    await callback.message.edit_text(f"✅ Semester updated to <b>{html.escape(sem)}</b>.", parse_mode="HTML")
    await callback.answer()

@router.message(Command("check_grades"))
async def cmd_check_grades(message: Message):
    async with SessionLocal() as db:
        from database.models import SystemSetting
        stmt = select(SystemSetting).where(SystemSetting.key == "is_scheduling_enabled")
        res = await db.execute(stmt)
        setting = res.scalar_one_or_none()
        if setting and setting.value == "false":
            await message.answer("⚠️ The grade checking service is currently disabled by Admin.")
            return

    # Year selection as required by app.md
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Year 1", callback_data="check_Y1"), InlineKeyboardButton(text="Year 2", callback_data="check_Y2")],
        [InlineKeyboardButton(text="Year 3", callback_data="check_Y3"), InlineKeyboardButton(text="Year 4", callback_data="check_Y4")],
        [InlineKeyboardButton(text="Year 5", callback_data="check_Y5"), InlineKeyboardButton(text="Year 6", callback_data="check_Y6")],
        [InlineKeyboardButton(text="Year 7", callback_data="check_Y7")],
        [InlineKeyboardButton(text="✨ All Years", callback_data="check_ALL")]
    ])
    
    await message.answer("Select the <b>Academic Year</b> you want to check:", reply_markup=kb, parse_mode="HTML")

@router.message(Command("refresh"))
async def cmd_refresh(message: Message):
    await cmd_check_grades(message)

@router.callback_query(F.data.startswith("check_"))
async def cb_perform_check(callback: CallbackQuery):
    year_map = {
        "check_Y1": "Year 1", "check_Y2": "Year 2", "check_Y3": "Year 3", "check_Y4": "Year 4",
        "check_Y5": "Year 5", "check_Y6": "Year 6", "check_Y7": "Year 7", "check_ALL": "All"
    }
    requested_year = year_map.get(callback.data, "All")
    
    await callback.answer()
    async with SessionLocal() as db:
        from services.grade_service import GradeService
        grade_service = GradeService(db)
        
        # 1. Fetch from DB first
        results = await grade_service.get_year_results(callback.from_user.id, requested_year)
        chunks = grade_service.format_grade_report(results, requested_year)
        
        # Prepare Audit
        from services.audit_service import AuditService
        await AuditService(db).log("VIEW_GRADE_DB", callback.from_user.id, {"year": requested_year})
        await db.commit()

        # 2. Display Chunks
        for i, chunk in enumerate(chunks):
            inline_kb = []
            if chunk.get("buttons"):
                for btn in chunk["buttons"]:
                    inline_kb.append([InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])])
            
            # Add Refresh button to the last chunk or alone if no results
            if i == len(chunks) - 1:
                inline_kb.append([InlineKeyboardButton(text="🔄 Force Refresh from Portal", callback_data=f"refresh_portal_{requested_year}")])
            
            kb = InlineKeyboardMarkup(inline_keyboard=inline_kb) if inline_kb else None
            
            if i == 0:
                await callback.message.edit_text(chunk["text"], reply_markup=kb, parse_mode="HTML")
            else:
                await callback.message.answer(chunk["text"], reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("view_asms_"))
async def cb_view_assessment(callback: CallbackQuery):
    grade_id = int(callback.data.replace("view_asms_", ""))
    async with SessionLocal() as db:
        from services.grade_service import GradeService
        from database.models import Grade
        grade_service = GradeService(db)
        
        stmt = select(Grade).where(Grade.id == grade_id)
        grade = (await db.execute(stmt)).scalar_one_or_none()
        
        if not grade:
            await callback.answer("Grade record not found.", show_alert=True)
            return

        # Try to find assessment matching this grade's course/year/sem
        # Using flexible lookup from GradeService
        assessment = await grade_service.get_stored_assessment(callback.from_user.id, grade.course_id)
        
        if not assessment:
            await callback.answer("Detailed assessment info not available in database.\n\nTry Force Refresh!", show_alert=True)
            return

        report = grade_service.format_assessment_detail(grade, assessment)
        await callback.message.answer(report, parse_mode="HTML")
        await callback.answer()

@router.callback_query(F.data.startswith("refresh_portal_"))
async def cb_refresh_portal(callback: CallbackQuery):
    requested_year = callback.data.replace("refresh_portal_", "")
    
    # 30-minute caching check
    from datetime import datetime, timedelta
    from sqlalchemy import desc
    from database.models import AuditLog
    
    async with SessionLocal() as db:
        thirty_mins_ago = datetime.utcnow() - timedelta(minutes=30)
        stmt = select(AuditLog).where(
            AuditLog.telegram_id == callback.from_user.id,
            AuditLog.action == "VIEW_GRADE_SCRAPE",
            AuditLog.timestamp > thirty_mins_ago
        ).order_by(desc(AuditLog.timestamp))
        res = await db.execute(stmt)
        # 🛡️ Fix: Use .first() instead of .scalar_one_or_none() because logs can have multiple entries
        last_check = res.scalars().first()
        
        if last_check:
            await callback.answer("⏳ Please wait 30 mins between portal refreshes.", show_alert=True)
            return

        # Log intent first
        from services.audit_service import AuditService
        await AuditService(db).log("VIEW_GRADE_SCRAPE", callback.from_user.id, {"year": requested_year})
        await db.commit()

    # Feedback to user
    await callback.answer("Scraping started!")
    yr_esc = html.escape(requested_year)
    await callback.message.answer(
        f"🔍 <b>Force Refresh Started</b> for {yr_esc}\n\n"
        f"I'm connecting to the AAU portal now. This usually takes 120-180 seconds.\n"
        f"I'll notify you here as soon as I have the latest results! ⏳",
        parse_mode="HTML"
    )
    
    # Trigger In-Process Background Task (Render Free Tier)
    from workers.tasks import run_check_user_grades
    asyncio.create_task(run_check_user_grades(callback.from_user.id, requested_year))

# --- Admin Interface ---

def is_admin(user_id: int) -> bool:
    admin_ids = os.getenv("ADMIN_IDS", "").split(",")
    return str(user_id) in admin_ids

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with SessionLocal() as db:
        from database.models import SystemSetting
        stmt = select(SystemSetting).where(SystemSetting.key == "is_scheduling_enabled")
        res = await db.execute(stmt)
        setting = res.scalar_one_or_none()
        status = "Enabled" if (not setting or setting.value == "true") else "Disabled"

    await message.answer(
        f"🛠 <b>Admin Dashboard</b>\n\n"
        f"Scheduler Status: <b>{status}</b>\n\n"
        "Commands:\n"
        "/start_service - Enable periodic checks\n"
        "/stop_service - Disable periodic checks\n"
        "/encrypt_db - 🔒 Migrate DB to AES-256",
        parse_mode="HTML"
    )

@router.message(Command("start_service"))
async def cmd_start_service(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with SessionLocal() as db:
        from database.models import SystemSetting
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(SystemSetting).values(
            key="is_scheduling_enabled", 
            value="true",
            description="Toggle for background grade checking"
        ).on_conflict_do_update(
            index_elements=["key"],
            set_={"value": "true"}
        )
        await db.execute(stmt)
        await db.commit()

    await message.answer("✅ Grade checking service <b>ENABLED</b>.", parse_mode="HTML")

@router.message(Command("stop_service"))
async def cmd_stop_service(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with SessionLocal() as db:
        from database.models import SystemSetting
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(SystemSetting).values(
            key="is_scheduling_enabled", 
            value="false",
            description="Toggle for background grade checking"
        ).on_conflict_do_update(
            index_elements=["key"],
            set_={"value": "false"}
        )
        await db.execute(stmt)
        await db.commit()

    await message.answer("🛑 Grade checking service <b>DISABLED</b>.", parse_mode="HTML")

@router.message(Command("encrypt_db"))
async def cmd_encrypt_db(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer("🔐 <b>Database Encryption Migration Started</b>\n\nI'm scanning for unencrypted records and securing them with AES-256. This may take a moment...", parse_mode="HTML")
    
    success_count = 0
    async with SessionLocal() as db:
        from database.models import Grade, Assessment, SemesterResult
        from services.credential_service import EncryptionService
        encryption_service = EncryptionService()
        
        # 1. Migrate Grades
        res = await db.execute(select(Grade).where(Grade.iv == None))
        grades = res.scalars().all()
        for g in grades:
            enc_grade, iv = encryption_service.encrypt_string(g.grade)
            g.grade = enc_grade
            g.iv = iv
            if g.course_name: g.course_name, _ = encryption_service.encrypt_string(g.course_name)
            if g.credit_hour: g.credit_hour, _ = encryption_service.encrypt_string(g.credit_hour)
            if g.ects: g.ects, _ = encryption_service.encrypt_string(g.ects)
            success_count += 1

        # 2. Migrate Assessments
        res = await db.execute(select(Assessment).where(Assessment.iv == None))
        assessments = res.scalars().all()
        for a in assessments:
            if a.assessment_data:
                enc_data, iv = encryption_service.encrypt_json(a.assessment_data)
                a.encrypted_data = enc_data
                a.iv = iv
                a.assessment_data = None
                success_count += 1

        # 3. Migrate Semester Results
        res = await db.execute(select(SemesterResult).where(SemesterResult.iv == None))
        results = res.scalars().all()
        for s in results:
            enc_sgpa, iv = encryption_service.encrypt_string(s.sgpa)
            s.sgpa = enc_sgpa
            s.cgpa, _ = encryption_service.encrypt_string(s.cgpa)
            s.status, _ = encryption_service.encrypt_string(s.status)
            s.iv = iv
            success_count += 1
            
        await db.commit()

    await message.answer(f"✅ <b>Encryption Complete!</b>\n\nSecured <code>{success_count}</code> records with AES-256-CBC.", parse_mode="HTML")
