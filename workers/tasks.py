# from workers.celery_app import celery_app (Removed for Render Free Tier)
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
import html

class PortalDownException(Exception):
    pass

async def run_check_all_grades():
    try:
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

            # Check portal hours (Portal is down from midnight to 6 AM East Africa Time)
            from datetime import datetime, timedelta
            import pytz
            eat = pytz.timezone('Africa/Addis_Ababa')
            current_time = datetime.now(eat)
            current_hour = current_time.hour
            
            if 0 <= current_hour < 6:
                logger.info(f"Grade check skipped: Portal is in maintenance hours (current hour: {current_hour}). Will retry after 6 AM.")
                await audit_service.log("CRON_GRADE_CHECK_SKIPPED", source="system", metadata={"reason": "maintenance_hours"})
                await db.commit()
                return

            user_service = UserService(db)
            grade_service = GradeService(db)
            notification_service = NotificationService()
            parser = PortalParser()
            
            # 🎯 Deduplication Logic: Group users by Department, Year Level, and Semester
            stmt = select(User.campus_id, User.department_id, User.academic_year, User.semester).group_by(
                User.campus_id, User.department_id, User.academic_year, User.semester
            )
            groups = (await db.execute(stmt)).all()
            
            for campus_id, dept_id, year, sem in groups:
                try:
                    # 🔄 Random Canary Selection
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
                        pc_client = None
                        try:
                            password = await user_service.get_decrypted_password(pc)
                            if not password: continue
                            
                            pc_client = PortalLoginClient()
                            pc_status, html = await asyncio.to_thread(pc_client.login, pc.university_id, password)
                            
                            if pc_status == "SUCCESS":
                                canary_user = pc
                                portal_client = pc_client
                                login_status = pc_status
                                # html is already populated from login()
                                break
                            elif pc_status == "BAD_CREDENTIALS":
                                pc.is_credential_valid = False
                                await db.commit()
                                await notification_service.send_notification(pc.telegram_id, "⚠️ Background check failed: <b>Invalid Portal Credentials</b>. Background checking is now <b>suspended</b> for your account. Please update your password using /my_data to resume tracking.")
                                logger.warning(f"Canary {pc.university_id} had bad credentials, moving to next candidate.")
                                pc_client.close()
                                pc_client = None
                            elif pc_status == "PORTAL_DOWN":
                                if pc_client:
                                    pc_client.close()
                                raise PortalDownException("Portal is down for canary candidate")
                        except PortalDownException:
                            raise
                        except Exception as e:
                            logger.error(f"Error checking candidate canary {pc.university_id}: {e}")
                            if pc_client:
                                pc_client.close()
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
                        if portal_client: portal_client.close()
                        continue

                    if not html: 
                        if portal_client: portal_client.close()
                        continue
                    
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
                    
                    if courses:
                        canary_user.academic_year = courses[0]['academic_year']
                        canary_user.semester = courses[0]['semester']
                    
                    summaries = result_data["summaries"]
                    
                    # Check summaries
                    for summary in summaries:
                        has_changed, msg = await grade_service.update_or_create_semester_result(canary_user.telegram_id, summary)
                        if has_changed and msg:
                            await audit_service.log("GPA_UPDATED", canary_user.telegram_id, {"year": summary['academic_year']})
                            await notification_service.send_notification(canary_user.telegram_id, msg)

                    group_has_updates = False
                    canary_course_codes = {c['course_code'] for c in courses}
                    
                    for course in courses:
                        grade_changed, grade_msg = await grade_service.update_or_create_grade(canary_user.telegram_id, course)
                        if grade_changed and grade_msg:
                            group_has_updates = True
                            await audit_service.log("GRADE_UPDATED", canary_user.telegram_id, {"course": course['course_code'], "type": "letter"})
                            await notification_service.send_notification(canary_user.telegram_id, grade_msg)

                        ids = course.get("assessment_ids", {})
                        if ids:
                            detail_html = await asyncio.to_thread(portal_client.get_assessment_detail_html,
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
                        
                        course_release_counts = {code: 1 for code in canary_course_codes}
                        
                        for u in other_users:
                            u_pw = await user_service.get_decrypted_password(u)
                            u_client = PortalLoginClient()
                            u_login_status, u_html = await asyncio.to_thread(u_client.login, u.university_id, u_pw)
                            
                            if u_login_status == "SUCCESS":
                                u_res = parser.parse_grade_report(u_html)
                                u_courses = u_res["courses"]
                                u_summaries = u_res["summaries"]
                                u_course_codes = {c['course_code'] for c in u_courses}
                                
                                if u_courses:
                                    u.academic_year = u_courses[0]['academic_year']
                                    u.semester = u_courses[0]['semester']
        
                                for code in u_course_codes:
                                    course_release_counts[code] = course_release_counts.get(code, 0) + 1
                                    
                                for s in u_summaries:
                                    h, m = await grade_service.update_or_create_semester_result(u.telegram_id, s)
                                    if h and m:
                                        await notification_service.send_notification(u.telegram_id, m)
        
                                for c in u_courses:
                                    gc, gm = await grade_service.update_or_create_grade(u.telegram_id, c)
                                    if gc and gm:
                                        await notification_service.send_notification(u.telegram_id, gm)
                                    
                                    c_ids = c.get("assessment_ids", {})
                                    if c_ids:
                                        c_detail = await asyncio.to_thread(u_client.get_assessment_detail_html, c_ids["academicYearId"], c_ids["semesterId"], c_ids["courseId"])
                                        if c_detail:
                                            a_data = parser.parse_assessment_detail(c_detail)
                                            u_has_changed, u_msg = await grade_service.update_or_create_assessment(u.telegram_id, c, a_data)
                                            if u_has_changed and u_msg:
                                                await notification_service.send_notification(u.telegram_id, u_msg)
                                
                                for code in (canary_course_codes - u_course_codes):
                                    esc_code = html.escape(code)
                                    await notification_service.send_notification(
                                        u.telegram_id, 
                                        f"ℹ️ Grade for <b>{esc_code}</b> is released for {course_release_counts.get(code, 1)} other students in your group, but not yet for you. Hang tight!"
                                    )
                                u_client.close()
                            elif u_login_status == "BAD_CREDENTIALS":
                                u.is_credential_valid = False
                                await notification_service.send_notification(u.telegram_id, "⚠️ Background check failed: <b>Invalid Portal Credentials</b>. Background checking is now <b>suspended</b> for your account. Please update your password using /my_data to resume tracking.")
                                u_client.close()
                            else:
                                if u_client: u_client.close()
                    
                    if portal_client: portal_client.close()
                    await db.commit()
                except PortalDownException:
                    logger.warning(f"Portal down for group {dept_id}, will retry on next cron")
                    if portal_client: portal_client.close()
                    continue
                except Exception as e:
                    logger.error(f"Error checking group {dept_id}: {e}")
                    if portal_client: portal_client.close()
                    continue
            
            await audit_service.log("CRON_GRADE_CHECK_END", source="system")
            await db.commit()
            await notification_service.close()
    except Exception as e:
        logger.error(f"Critical error in run_check_all_grades: {e}")

async def run_check_user_grades(telegram_id: int, requested_year: str = "All"):
    try:
        async with SessionLocal() as db:
            user_service = UserService(db)
            grade_service = GradeService(db)
            notification_service = NotificationService()
            parser = PortalParser()
            audit_service = AuditService(db)

            # Check portal hours (Portal is down from midnight to 6 AM East Africa Time)
            from datetime import datetime
            import pytz
            eat = pytz.timezone('Africa/Addis_Ababa')
            current_time = datetime.now(eat)
            current_hour = current_time.hour
            
            if 0 <= current_hour < 6:
                logger.info(f"Manual grade check skipped for user {telegram_id}: Portal is in maintenance hours (current hour: {current_hour}).")
                await notification_service.send_notification(
                    telegram_id, 
                    f"⏰ The AAU portal is currently under maintenance (midnight - 6 AM). Please try again after 6:00 AM. Current time: <code>{html.escape(current_time.strftime('%I:%M %p'))}</code>"
                )
                await notification_service.close()
                return

            user = await user_service.get_user_by_telegram_id(telegram_id)
            if not user: return

            password = await user_service.get_decrypted_password(user)
            if not password: return

            # Retry logic for portal down scenarios
            max_retries = 3
            retry_delays = [120, 300, 600]  # 2 min, 5 min, 10 min
            
            for attempt in range(max_retries):
                portal_client = None
                try:
                    portal_client = PortalLoginClient()
                    logger.info(f"⏳ Attempting portal login for {user.university_id}... (Attempt {attempt + 1}/{max_retries})")
                    login_status, html = await asyncio.to_thread(portal_client.login, user.university_id, password)
                    
                    if login_status == "SUCCESS":
                        logger.info("🔑 Login successful. Parsing grades...")
                        if html:
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
                                if not GradeService.matches_year(s, requested_year):
                                    continue
                                h, m = await grade_service.update_or_create_semester_result(user.telegram_id, s)
                                if h and m:
                                    updates_found += 1
                                    await notification_service.send_notification(telegram_id, m)

                            # Check courses
                            for course in courses:
                                if not GradeService.matches_year(course, requested_year):
                                    continue
                                # Final Letter
                                gc, gm = await grade_service.update_or_create_grade(user.telegram_id, course)
                                if gc and gm:
                                    updates_found += 1
                                    await notification_service.send_notification(telegram_id, gm)

                                # Detail
                                ids = course.get("assessment_ids", {})
                                if ids:
                                    detail_html = await asyncio.to_thread(portal_client.get_assessment_detail_html,
                                        ids["academicYearId"], ids["semesterId"], ids["courseId"]
                                    )
                                    if detail_html:
                                        assessment_data = parser.parse_assessment_detail(detail_html)
                                        has_changed, msg = await grade_service.update_or_create_assessment(
                                            user.telegram_id, course, assessment_data
                                        )
                                        if has_changed and msg:
                                            updates_found += 1
                                            await audit_service.log("GRADE_UPDATED", telegram_id, {"course": course['course_code'], "type": "detail"})
                                            await notification_service.send_notification(telegram_id, msg)
                            
                            await db.commit()
                            
                            # Phase 3 detection: If requested a specific year and no courses matched
                            if requested_year != "All":
                                matching = [c for c in courses if GradeService.matches_year(c, requested_year)]
                                if not matching:
                                    await notification_service.send_notification(
                                        telegram_id,
                                        f"📭 <b>Year Results Not Found</b>\n\n"
                                        f"I checked the portal but couldn't find any results for <b>{html.escape(requested_year)}</b>.\n\n"
                                        f"This usually means:\n"
                                        f"• Results for this year haven't been released yet.\n"
                                        f"• You haven't reached this academic year level yet.\n\n"
                                        f"Try checking <b>✨ All Years</b> to see what's currently available."
                                    )
                                    portal_client.close()
                                    break

                            if updates_found == 0:
                                await notification_service.send_notification(telegram_id, f"✅ Portal check for <b>{html.escape(requested_year)}</b> finished. No new updates found.")
                            else:
                                await notification_service.send_notification(telegram_id, f"✅ Portal check finished. Applied {updates_found} updates.")
                        
                        # Success - cleanup and break out of retry loop
                        portal_client.close()
                        break
                    
                    elif login_status == "BAD_CREDENTIALS":
                        user.is_credential_valid = False
                        await db.commit()
                        await notification_service.send_notification(telegram_id, "❌ <b>Login failed!</b> Your portal credentials appear to be incorrect.\n\nBackground checking has been <b>suspended</b>. Please update them using /my_data.")
                        portal_client.close()
                        break  # Don't retry for bad credentials
                    
                    else:  # PORTAL_DOWN
                        portal_client.close()
                        if attempt < max_retries - 1:
                            delay = retry_delays[attempt]
                            logger.warning(f"Portal down. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                            await notification_service.send_notification(telegram_id, f"⚠️ Portal is down. Retrying in <b>{delay // 60} minutes</b>... (Attempt {attempt + 1}/{max_retries})")
                            await asyncio.sleep(delay)
                        else:
                            logger.error(f"Portal down after {max_retries} attempts. Giving up.")
                            await notification_service.send_notification(telegram_id, "❌ The portal is currently down. I've tried multiple times but couldn't connect. I'll try again during the next scheduled check.")
                            
                except Exception as e:
                    logger.error(f"Unexpected error during grade check: {e}")
                    if portal_client:
                        portal_client.close()
                    if attempt == max_retries - 1:
                        await notification_service.send_notification(telegram_id, f"❌ An error occurred while checking grades: <code>{html.escape(str(e))}</code>")
                    break
            
            await notification_service.close()
    except Exception as e:
        logger.error(f"Critical background task error for user {telegram_id}: {e}")
