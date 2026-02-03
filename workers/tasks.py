from workers.celery_app import celery_app
from database.connection import SessionLocal
from database.models import User
from services.user_service import UserService
from services.grade_service import GradeService
from services.notification_service import NotificationService
from portal.login_client import PortalLoginClient
from portal.parser import PortalParser
from sqlalchemy import select
import asyncio
import logging

logger = logging.getLogger(__name__)

from services.audit_service import AuditService
from sqlalchemy import func

class PortalDownException(Exception):
    pass

async def run_check_all_grades():
    async with SessionLocal() as db:
        audit_service = AuditService(db)
        await audit_service.log("CRON_GRADE_CHECK_START", source="system")

        # Check if service is enabled
        from database.models import SystemSetting, GradeCheckStatus
        stmt = select(SystemSetting).where(SystemSetting.key == "is_scheduling_enabled")
        res = await db.execute(stmt)
        setting = res.scalar_one_or_none()
        if setting and setting.value == "false":
            logger.info("Grade check skipped: Service is disabled.")
            return

        user_service = UserService(db)
        grade_service = GradeService(db)
        notification_service = NotificationService()
        parser = PortalParser()
        
        # 🎯 Deduplication Logic: Group users by Department, Year Level, and Semester
        # Using a simplistic grouping by (campus, department) for now
        stmt = select(User.campus_id, User.department_id, User.academic_year, User.semester).group_by(
            User.campus_id, User.department_id, User.academic_year, User.semester
        )
        groups = (await db.execute(stmt)).all()
        
        for campus_id, dept_id, year, sem in groups:
            # 🔄 Random Canary Selection for Fairness and Resilience
            # Fetch all users in the group who have valid credentials
            stmt = select(User).where(
                User.campus_id == campus_id,
                User.department_id == dept_id,
                User.academic_year == year,
                User.semester == sem,
                User.is_credential_valid == True
            )
            potential_canaries = (await db.execute(stmt)).scalars().all()
            
            if not potential_canaries:
                continue

            import random
            random.shuffle(potential_canaries)
            
            canary_user = None
            portal_client = None
            login_status = None
            
            # Try potential canaries until one succeeds or we run out
            for pc in potential_canaries:
                try:
                    password = await user_service.get_decrypted_password(pc)
                    if not password: continue
                    
                    pc_client = PortalLoginClient()
                    pc_status = pc_client.login(pc.university_id, password)
                    
                    if pc_status == "SUCCESS":
                        canary_user = pc
                        portal_client = pc_client
                        login_status = pc_status
                        break
                    elif pc_status == "BAD_CREDENTIALS":
                        pc.is_credential_valid = False
                        await db.commit()
                        await notification_service.send_notification(pc.telegram_id, "⚠️ Background check failed: **Invalid Portal Credentials**. Background checking is now **suspended** for your account. Please update your password using /my_data to resume tracking.")
                        logger.warning(f"Canary {pc.university_id} had bad credentials, moving to next candidate.")
                    elif pc_status == "PORTAL_DOWN":
                        # If portal is actually down, we stop the whole group check and retry later
                        raise PortalDownException("Portal is down for canary candidate")
                except PortalDownException:
                    raise
                except Exception as e:
                    logger.error(f"Error checking candidate canary {pc.university_id}: {e}")
                    continue

            if not canary_user:
                logger.warning(f"Could not find a valid canary for group {dept_id} {year}.")
                continue

            # Check if we checked this group recently (e.g., 30 mins)
            status_stmt = select(GradeCheckStatus).where(
                GradeCheckStatus.campus_id == campus_id,
                GradeCheckStatus.department_id == dept_id,
                GradeCheckStatus.academic_year == year,
                GradeCheckStatus.semester == sem
            )
            status_res = await db.execute(status_stmt)
            status = status_res.scalar_one_or_none()
            
            if status and (datetime.utcnow() - status.last_checked_at).total_seconds() < 1800:
                logger.info(f"Skipping group {dept_id} {year}: Recently checked.")
                continue

            try:
                html = portal_client.get_grade_report_html()
                if not html: continue
                
                # If we got here, mark as checked
                if not status:
                    status = GradeCheckStatus(
                        campus_id=campus_id, department_id=dept_id,
                        academic_year=year, semester=sem,
                        last_full_sync_at=datetime.utcnow() - timedelta(days=2) # Force first sync
                    )
                    db.add(status)
                status.last_checked_at = datetime.utcnow()

                result_data = parser.parse_grade_report(html)
                courses = result_data["courses"]
                
                # Sync canary status
                if courses:
                    canary_user.academic_year = courses[0]['academic_year']
                    canary_user.semester = courses[0]['semester']
                
                summaries = result_data["summaries"]
                
                # Check summaries (GPA) for canary
                for summary in summaries:
                    has_changed, msg = await grade_service.update_or_create_semester_result(canary_user.telegram_id, summary)
                    if has_changed and msg:
                        await audit_service.log("GPA_UPDATED", canary_user.telegram_id, {"year": summary['academic_year']})
                        await notification_service.send_notification(canary_user.telegram_id, msg)

                # Check if ANY grade or assessment changed for the canary
                group_has_updates = False
                canary_course_codes = {c['course_code'] for c in courses}
                
                for course in courses:
                    # 1. Check Final Grade Letter (A, B, etc.)
                    grade_changed, grade_msg = await grade_service.update_or_create_grade(canary_user.telegram_id, course)
                    if grade_changed and grade_msg:
                        group_has_updates = True
                        await audit_service.log("GRADE_UPDATED", canary_user.telegram_id, {"course": course['course_code'], "type": "letter"})
                        await notification_service.send_notification(canary_user.telegram_id, grade_msg)

                    # 2. Check Detailed Assessment Data
                    ids = course.get("assessment_ids", {})
                    if ids:
                        detail_html = portal_client.get_assessment_detail_html(
                            ids["academicYearId"], ids["semesterId"], ids["courseId"]
                        )
                        if detail_html:
                            assessment_data = parser.parse_assessment_detail(detail_html)
                            assess_changed, assess_msg = await grade_service.update_or_create_assessment(
                                canary_user.telegram_id, course, assessment_data
                            )
                            if assess_changed:
                                group_has_updates = True
                                if assess_msg: 
                                    await audit_service.log("GRADE_UPDATED", canary_user.telegram_id, {"course": course['course_code'], "type": "detail"})
                                    await notification_service.send_notification(canary_user.telegram_id, assess_msg)
                
                # If Canary has updates OR it's time for a periodic full sync (e.g., 24h)
                needs_full_sync = group_has_updates or (
                    not status.last_full_sync_at or 
                    (datetime.utcnow() - status.last_full_sync_at).total_seconds() > 86400
                )

                if needs_full_sync:
                    status.last_full_sync_at = datetime.utcnow()
                    stmt = select(User).where(
                        User.campus_id == campus_id,
                        User.department_id == dept_id,
                        User.academic_year == year,
                        User.semester == sem,
                        User.id != canary_user.id,
                        User.is_credential_valid == True
                    )
                    other_users = (await db.execute(stmt)).scalars().all()
                    
                    # Track who has which grade for the specific "released count" logic
                    course_release_counts = {code: 1 for code in canary_course_codes} # Canary already has them
                    
                    for u in other_users:
                        u_pw = await user_service.get_decrypted_password(u)
                        u_client = PortalLoginClient()
                        login_status = u_client.login(u.university_id, u_pw)
                        
                        if login_status == "SUCCESS":
                            u_res = parser.parse_grade_report(u_client.get_grade_report_html())
                            u_courses = u_res["courses"]
                            u_summaries = u_res["summaries"]
                            u_course_codes = {c['course_code'] for c in u_courses}
                            
                            # Sync user status
                            if u_courses:
                                u.academic_year = u_courses[0]['academic_year']
                                u.semester = u_courses[0]['semester']
    
                            # Update counts
                            for code in u_course_codes:
                                course_release_counts[code] = course_release_counts.get(code, 0) + 1
                                
                            # Check everything for this user
                            for s in u_summaries:
                                h, m = await grade_service.update_or_create_semester_result(u.telegram_id, s)
                                if h and m:
                                    await notification_service.send_notification(u.telegram_id, m)
    
                            for c in u_courses:
                                # Final Letter
                                gc, gm = await grade_service.update_or_create_grade(u.telegram_id, c)
                                if gc and gm:
                                    await notification_service.send_notification(u.telegram_id, gm)
                                
                                # Detail
                                c_ids = c.get("assessment_ids", {})
                                if c_ids:
                                    c_detail = u_client.get_assessment_detail_html(c_ids["academicYearId"], c_ids["semesterId"], c_ids["courseId"])
                                    if c_detail:
                                        a_data = parser.parse_assessment_detail(c_detail)
                                        u_has_changed, u_msg = await grade_service.update_or_create_assessment(u.telegram_id, c, a_data)
                                        if u_has_changed and u_msg:
                                            await notification_service.send_notification(u.telegram_id, u_msg)
                            
                            # "Released for X students" logic
                            for code in (canary_course_codes - u_course_codes):
                                await notification_service.send_notification(
                                    u.telegram_id, 
                                    f"ℹ️ Grade for {code} is released for {course_release_counts.get(code, 1)} other students in your group, but not yet for you. Hang tight!"
                                )
                        elif login_status == "BAD_CREDENTIALS":
                            u.is_credential_valid = False
                            await notification_service.send_notification(u.telegram_id, "⚠️ Background check failed: **Invalid Portal Credentials**. Background checking is now **suspended** for your account. Please update your password using /my_data to resume tracking.")
                
                await db.commit()
            except Exception as e:
                logger.error(f"Error checking group {dept_id}: {e}")
        
        await audit_service.log("CRON_GRADE_CHECK_END", source="system")
        await db.commit()
        await notification_service.close()

async def run_check_user_grades(telegram_id: int, requested_year: str = "All"):
    async with SessionLocal() as db:
        user_service = UserService(db)
        grade_service = GradeService(db)
        notification_service = NotificationService()
        parser = PortalParser()
        audit = AuditService(db)

        user = await user_service.get_user_by_telegram_id(telegram_id)
        if not user: return

        password = await user_service.get_decrypted_password(user)
        if not password: return

        portal_client = PortalLoginClient()
        logger.info(f"⏳ Attempting portal login for {user.university_id}...")
        login_status = portal_client.login(user.university_id, password)
        
        if login_status == "SUCCESS":
            logger.info("🔑 Login successful. Fetching grade report HTML...")
            html = portal_client.get_grade_report_html()
            if html:
                logger.info("📄 HTML received. Parsing grades...")
                res_data = parser.parse_grade_report(html)
                courses = res_data["courses"]
                
                # Update user's academic year/semester from latest scrape if available
                if courses:
                    user.academic_year = courses[0]['academic_year']
                    user.semester = courses[0]['semester']
                summaries = res_data["summaries"]
                
                logger.info(f"📊 Found {len(courses)} courses and {len(summaries)} semester summaries. Checking for updates...")
                updates_found = 0
                
                # Check summaries
                for s in summaries:
                    if requested_year != "All" and requested_year not in s["academic_year"]:
                        continue
                    h, m = await grade_service.update_or_create_semester_result(user.telegram_id, s)
                    if h and m:
                        updates_found += 1
                        await notification_service.send_notification(telegram_id, m)

                # Check courses
                for course in courses:
                    if requested_year != "All" and requested_year not in course["academic_year"]:
                        continue
                    # Final Letter
                    gc, gm = await grade_service.update_or_create_grade(user.telegram_id, course)
                    if gc and gm:
                        updates_found += 1
                        await notification_service.send_notification(telegram_id, gm)

                    # Detail
                    ids = course.get("assessment_ids", {})
                    if ids:
                        detail_html = portal_client.get_assessment_detail_html(
                            ids["academicYearId"], ids["semesterId"], ids["courseId"]
                        )
                        if detail_html:
                            assessment_data = parser.parse_assessment_detail(detail_html)
                            has_changed, msg = await grade_service.update_or_create_assessment(
                                user.telegram_id, course, assessment_data
                            )
                            if has_changed and msg:
                                updates_found += 1
                                await audit.log("GRADE_UPDATED", telegram_id, {"course": course['course_code'], "type": "detail"})
                                await notification_service.send_notification(telegram_id, msg)
                
                await db.commit()
                if updates_found == 0:
                    await notification_service.send_notification(telegram_id, f"✅ Portal check for **{requested_year}** finished. No new updates found.")
                else:
                    await notification_service.send_notification(telegram_id, f"✅ Portal check finished. Applied {updates_found} updates.")
        
        elif login_status == "BAD_CREDENTIALS":
            user.is_credential_valid = False
            await db.commit()
            await notification_service.send_notification(telegram_id, "❌ **Login failed!** Your portal credentials appear to be incorrect.\n\nBackground checking has been **suspended**. Please update them using /my_data.")
        else:
            await notification_service.send_notification(telegram_id, "❌ The portal is currently down or unresponsive. I will retry periodically.")
            raise PortalDownException("Portal is down")
        
        await notification_service.close()

@celery_app.task(
    name="workers.tasks.check_user_grades",
    autoretry_for=(PortalDownException,),
    retry_backoff=True,
    max_retries=5
)
def check_user_grades_task(telegram_id: int, requested_year: str = "All"):
    logger.info(f"🚀 TASK START: Manual grade check for {telegram_id} (Year: {requested_year})")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_check_user_grades(telegram_id, requested_year))
        logger.info(f"✅ TASK COMPLETE: Manual grade check for {telegram_id}")
    finally:
        loop.close()

@celery_app.task(
    name="workers.tasks.check_all_grades",
    autoretry_for=(PortalDownException,),
    retry_backoff=True,
    max_retries=5
)
def check_all_grades():
    logger.info("🚀 TASK START: Periodic background check (All Users)")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_check_all_grades())
        logger.info("✅ TASK COMPLETE: Periodic background check")
    finally:
        loop.close()
