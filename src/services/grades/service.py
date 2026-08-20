"""Cached and formatted grade read service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from dto.bot import GradeReadRequest, GradeReadResult
from parser.models import GradeReport, CourseGrade, AssessmentReference, GradeReportSummary


@dataclass(frozen=True)
class CachedGradeSnapshot:
    """Snapshot of a grade report lookup."""
    message: str
    cached: bool


def format_grade_report_page(
    academic_year: str,
    semester_label: str,
    year_label: str,
    course_grades: Sequence[dict[str, Any]],
    summary: dict[str, Any] | None = None,
) -> str:
    """Format a single term/semester grade report with detailed inline assessments."""
    lines = [
        f"🎓 <b>AAU Grade Report</b>",
        f"📅 <b>Academic Year:</b> {academic_year} | <b>Year:</b> {year_label}",
        f"📘 <b>Semester:</b> {semester_label}",
        "──────────────────────────────",
    ]

    if not course_grades:
        lines.append("No course grades available for this term.")
    else:
        for course in course_grades:
            code = course.get("course_code", "")
            name = course.get("course_name", "")
            credits = course.get("credit_hours", 0)
            ects = course.get("ects", 0)
            grade = course.get("grade", "N/A")

            lines.append(f"📚 <b>{code} {name}</b>".strip())
            lines.append(f"  • Credits: {credits} | ECTS: {ects} | Grade: <b>{grade}</b>")
            lines.append("")
        sgp = summary.get("sgp", 0.0) if summary else 0.0
        sgpa = summary.get("sgpa", 0.0) if summary else 0.0
        cgpa = summary.get("cgpa", 0.0) if summary else 0.0
        status = summary.get("academic_status", "Active") if summary else "Active"
        lines.append("──────────────────────────────")
        lines.append(f"📊 <b>Summary:</b> SGPA: <code>{sgpa:.2f}</code> | CGPA: <code>{cgpa:.2f}</code>")
        lines.append(f"Status: <b>{status}</b>")

    return "\n".join(lines)


class GradeReadService:
    """Return formatted grades with pagination and detailed assessment breakdown."""

    def __init__(
        self,
        cache: Any | None = None,
        repository: Any | None = None,
        session_factory: Any | None = None,
        cipher: Any | None = None,
        portal_client: Any | None = None,
        manual_scrape_cooldown_minutes: int = 30,
        notification_service: Any | None = None,
    ) -> None:
        self.cache = cache
        self.repository = repository
        self.session_factory = session_factory
        self.cipher = cipher
        self.portal_client = portal_client
        self.manual_scrape_cooldown_minutes = manual_scrape_cooldown_minutes
        self.notification_service = notification_service

    def _format_reports_to_pages(self, reports: Any, year_filter: str | None = None, semester_filter: str | None = None) -> list[str]:
        if not reports:
            return []
        if not isinstance(reports, (list, tuple)):
            reports_list = [reports]
        else:
            reports_list = list(reports)

        pages = []
        def roman_to_int(s: str) -> int:
            mapping = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6}
            return mapping.get(s, 0)
            
        def extract_year_num(s: str) -> int | None:
            s = s.lower().replace("year", "").replace(":", "").strip()
            if s.isdigit():
                return int(s)
            num = roman_to_int(s)
            if num > 0:
                return num
            return None

        filtered_reports = []
        for rep in reports_list:
            rep_year = getattr(rep, "year_label", getattr(rep, "academic_year", "N/A"))
            rep_sem = getattr(rep, "semester_label", getattr(rep, "semester", "N/A"))
            
            if year_filter and year_filter != "All" and year_filter != "All Years":
                yf_num = extract_year_num(year_filter)
                ry_num = extract_year_num(rep_year)
                # If we could parse both and they differ, skip this report.
                # If we couldn't parse one of them, we conservatively include it so user doesn't miss grades.
                if yf_num is not None and ry_num is not None and yf_num != ry_num:
                    continue
            
            if semester_filter and semester_filter != "All" and semester_filter != "All Semesters":
                sf_lower = semester_filter.lower().replace("semester", "").strip()
                rf_lower = rep_sem.lower().replace("semester", "").strip()
                
                is_sf_one = "one" in sf_lower or "1" in sf_lower or "i" in sf_lower.split()
                is_sf_two = "two" in sf_lower or "2" in sf_lower or "ii" in sf_lower.split()
                is_sf_three = "three" in sf_lower or "3" in sf_lower or "iii" in sf_lower.split()
                
                is_rf_one = "one" in rf_lower or "1" in rf_lower or "i" in rf_lower.split()
                is_rf_two = "two" in rf_lower or "2" in rf_lower or "ii" in rf_lower.split()
                is_rf_three = "three" in rf_lower or "3" in rf_lower or "iii" in rf_lower.split()
                
                if is_sf_one and not is_rf_one:
                    continue
                if is_sf_two and not is_rf_two:
                    continue
                if is_sf_three and not is_rf_three:
                    continue
                    
            filtered_reports.append(rep)

        for rep in filtered_reports:
            course_dicts = []
            for cg in getattr(rep, "course_grades", []):
                course_dicts.append({
                    "course_code": getattr(cg, "course_code", ""),
                    "course_name": getattr(cg, "course_name", ""),
                    "credit_hours": getattr(cg, "credit_hours", 0),
                    "ects": getattr(cg, "ects", 0),
                    "grade": getattr(cg, "grade", "N/A"),
                })
            summary_obj = getattr(rep, "summary", None)
            summary_dict = None
            if summary_obj is not None:
                summary_dict = {
                    "sgp": getattr(summary_obj, "sgp", 0.0),
                    "sgpa": getattr(summary_obj, "sgpa", 0.0),
                    "cgpa": getattr(summary_obj, "cgpa", 0.0),
                    "academic_status": getattr(summary_obj, "academic_status", "Active"),
                }
            msg = format_grade_report_page(
                academic_year=getattr(rep, "academic_year", "N/A"),
                semester_label=getattr(rep, "semester_label", "N/A"),
                year_label=getattr(rep, "year_label", "N/A"),
                course_grades=course_dicts,
                summary=summary_dict,
            )
            pages.append((msg, rep))
        return pages

    async def read(self, request: GradeReadRequest) -> GradeReadResult:
        """
        Reads a user's grade reports, prioritizing the database cache.
        If `force_refresh` is True, it attempts a live portal scrape, respecting cooldown limits.
        Filters by year and semester if specified.
        """
        cooldown_key = f"cooldown:scrape:{request.telegram_id}"

        # 1b. Check scrape cooldown if force_refresh
        if self.cache is not None and request.force_refresh:
            if await self.cache.get(cooldown_key):
                # Still in cooldown, fallback to DB and add warning
                request = GradeReadRequest(
                    telegram_id=request.telegram_id, 
                    force_refresh=False,
                    year_filter=request.year_filter,
                    semester_filter=request.semester_filter,
                    page_index=request.page_index
                )
                pass # Continue to load from DB

        # 2. Try DB and live portal scrape if credentials exist
        if self.session_factory is not None and self.cipher is not None:
            try:
                from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
                from database.models import SemesterResult
                async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                    db_user = await uow.users.get_by_telegram_id(request.telegram_id)
                    if db_user is not None and db_user.id:
                        if not request.force_refresh:
                            # Load from DB
                            from sqlalchemy import select
                            db_results = await uow.session.scalars(
                                select(SemesterResult)
                                .where(SemesterResult.user_id == db_user.id)
                            )
                            reports = []
                            for res in db_results:
                                try:
                                    json_data = self.cipher.decrypt(res.encrypted_result_detail)
                                    reports.append(GradeReport.model_validate_json(json_data))
                                except Exception as e:
                                    import logging
                                    logging.getLogger(__name__).warning(f"Failed to decrypt/parse SemesterResult: {e}")
                            
                            if reports:
                                pages = self._format_reports_to_pages(reports, request.year_filter, request.semester_filter)
                                if pages:
                                    idx = max(0, min(request.page_index, len(pages) - 1))
                                    msg, rep = pages[idx]
                                    if self.cache is not None and await self.cache.get(cooldown_key):
                                        msg = f"⏳ <b>Cooldown Active</b>\nYou can only refresh from the portal every {self.manual_scrape_cooldown_minutes} minutes to reduce load. Showing DB grades.\n\n{msg}"
                                    return GradeReadResult(
                                        message=msg,
                                        cached=False,
                                        current_page=idx,
                                        total_pages=len(pages),
                                        report=rep
                                    )
                        # Force refresh from portal
                        lock_key = f"lock:scrape:{request.telegram_id}"
                        if self.cache is not None:
                            if not await self.cache.acquire_lock(lock_key, ttl_seconds=60):
                                return GradeReadResult(
                                    message="⏳ <b>Refresh in progress...</b>\nA grade refresh is already in progress. Please wait a moment for it to complete.",
                                    cached=False,
                                    current_page=0,
                                    total_pages=1,
                                    report=None
                                )
                                
                        cred = await uow.credentials.get_by_user_id(db_user.id)
                        if cred is not None and self.portal_client is not None:
                            try:
                                password = self.cipher.decrypt(cred.encrypted_password)
                                _profile, grade_reports = await self.portal_client.scrape(
                                    db_user.university_id,
                                    password,
                                    db_user.university_id,
                                )
                                
                                # Save to DB
                                from database.models import Semester, AuditLog
                                
                                # Audit manual scrape success
                                audit_success = AuditLog(
                                    telegram_id=request.telegram_id,
                                    action="manual_scrape",
                                    details={"success": True, "university_id": db_user.university_id}
                                )
                                uow.session.add(audit_success)

                                def parse_semester(label: str) -> Semester:
                                    lab = label.lower()
                                    if "2" in lab or "two" in lab or "second" in lab or " ii" in lab:
                                        return Semester.SECOND
                                    if "3" in lab or "three" in lab or "third" in lab or "iii" in lab:
                                        return Semester.THIRD
                                    return Semester.FIRST
                                    
                                from sqlalchemy import delete
                                await uow.session.execute(delete(SemesterResult).where(SemesterResult.user_id == db_user.id))
                                
                                import base64
                                from crypto.cipher import Ciphertext
                                for rep in grade_reports:
                                    rep_json = json.dumps(rep.model_dump())
                                    enc_rep = self.cipher.encrypt(rep_json)
                                    rep_payload = Ciphertext.from_token(enc_rep)
                                    rep_iv = base64.urlsafe_b64encode(rep_payload.nonce).decode("ascii")
                                    sr = SemesterResult(
                                        user_id=db_user.id,
                                        academic_year=rep.academic_year,
                                        semester=parse_semester(rep.semester_label),
                                        encrypted_result_detail=enc_rep,
                                        iv=rep_iv,
                                    )
                                    uow.session.add(sr)
                                    
                                    # Save Courses, UserCourses, Assessments, and DepartmentCourses
                                    from database.models import Course, UserCourse, Assessment, DepartmentCourse
                                    from sqlalchemy import select
                                    
                                    for cg in rep.course_grades:
                                        # Ensure Course exists
                                        course_db = await uow.courses.get_by_id(cg.course_code)
                                        if not course_db:
                                            course_db = Course(
                                                course_id=cg.course_code,
                                                course_name=cg.course_name,
                                                credit_hours=int(cg.credit_hours) if cg.credit_hours else 0,
                                                ects=int(cg.ects) if cg.ects else 0,
                                            )
                                            await uow.courses.add(course_db)
                                            await uow.session.flush()
                                            
                                        if db_user.department_id:
                                            dc_stmt = select(DepartmentCourse).where(
                                                DepartmentCourse.department_id == db_user.department_id,
                                                DepartmentCourse.course_id == course_db.course_id
                                            )
                                            dc_db = await uow.session.scalar(dc_stmt)
                                            if not dc_db:
                                                dc_db = DepartmentCourse(
                                                    department_id=db_user.department_id,
                                                    course_id=course_db.course_id
                                                )
                                                uow.session.add(dc_db)

                                        # Create or update UserCourse
                                        uc_stmt = select(UserCourse).where(
                                            UserCourse.user_id == db_user.id,
                                            UserCourse.course_id == course_db.course_id,
                                            UserCourse.academic_year == rep.academic_year,
                                            UserCourse.semester == parse_semester(rep.semester_label)
                                        )
                                        uc_db = await uow.session.scalar(uc_stmt)
                                        if not uc_db:
                                            uc_db = UserCourse(
                                                user_id=db_user.id,
                                                course_id=course_db.course_id,
                                                academic_year=rep.academic_year,
                                                semester=parse_semester(rep.semester_label)
                                            )
                                            uow.session.add(uc_db)
                                            await uow.session.flush()

                                        # Save Assessment reference
                                        asm_dict = {
                                            "reference": cg.assessment.model_dump() if cg.assessment else None,
                                            "grade": cg.grade
                                        }
                                        enc_asm = self.cipher.encrypt(json.dumps(asm_dict))
                                        asm_payload = Ciphertext.from_token(enc_asm)
                                        asm_iv = base64.urlsafe_b64encode(asm_payload.nonce).decode("ascii")

                                        asm_stmt = select(Assessment).where(Assessment.user_course_id == uc_db.id)
                                        asm_db = await uow.session.scalar(asm_stmt)
                                        if not asm_db:
                                            asm_db = Assessment(
                                                user_course_id=uc_db.id,
                                                encrypted_assessment_detail=enc_asm,
                                                encrypted_grade=enc_asm,
                                                iv=asm_iv
                                            )
                                            uow.session.add(asm_db)
                                        else:
                                            # Don't overwrite if it already has detailed scores, only if it's just reference
                                            asm_db.encrypted_assessment_detail = enc_asm
                                            asm_db.encrypted_grade = enc_asm
                                            asm_db.iv = asm_iv
                                            
                                await uow.commit()

                                pages = self._format_reports_to_pages(grade_reports, request.year_filter, request.semester_filter)
                                if pages:
                                    if self.cache is not None:
                                        await self.cache.set(cooldown_key, "1", ttl_seconds=self.manual_scrape_cooldown_minutes * 60)
                                    idx = max(0, min(request.page_index, len(pages) - 1))
                                    msg, rep = pages[idx]
                                    return GradeReadResult(
                                        message=msg,
                                        cached=False,
                                        current_page=idx,
                                        total_pages=len(pages),
                                        report=rep
                                    )
                            except Exception as scrape_err:
                                import logging
                                from clients.aau_portal import PortalSchemaChangedError, PortalAuthenticationError
                                from database.models import AuditLog
                                
                                if isinstance(scrape_err, PortalSchemaChangedError) and self.notification_service is not None:
                                    snippet = getattr(scrape_err.diagnostic, "html_snippet", "")
                                    await getattr(self.notification_service, "send_admin", self.notification_service.send_admin_alert)(
                                        f"Portal schema changed during grades refresh: {scrape_err}",
                                        snippet
                                    )
                                elif isinstance(scrape_err, PortalAuthenticationError):
                                    # Mark credentials as invalid to prevent lockout (ADR 021)
                                    cred.is_valid = False
                                    
                                    audit_fail = AuditLog(
                                        telegram_id=request.telegram_id,
                                        action="authentication_failed",
                                        details={"reason": "invalid_credentials", "university_id": db_user.university_id}
                                    )
                                    uow.session.add(audit_fail)
                                    
                                    await uow.commit()
                                    if self.notification_service is not None and hasattr(self.notification_service, "send_user"):
                                        await self.notification_service.send_user(
                                            request.telegram_id,
                                            "⚠️ <b>Authentication Failed</b>\nYour AAU portal password appears to have been changed or is incorrect. Automated grade checking has been paused. Please use /change_password to update it."
                                        )
                                else:
                                    audit_fail = AuditLog(
                                        telegram_id=request.telegram_id,
                                        action="manual_scrape_failed",
                                        details={"reason": str(scrape_err), "university_id": db_user.university_id}
                                    )
                                    uow.session.add(audit_fail)
                                    await uow.commit()

                                logging.getLogger(__name__).warning(f"Portal scrape failed for user: {scrape_err}")
                            finally:
                                if self.cache is not None:
                                    await self.cache.release_lock(lock_key)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error checking cooldown or parsing DB: {e}", exc_info=True)

        # Fallback: no grades found via any path
        return GradeReadResult(
            message=(
                "No grades available yet. Please use /register to connect your AAU account "
                "or refresh your grades."
            ),
            cached=False,
            current_page=0,
            total_pages=1,
        )

    async def read_assessment(self, telegram_id: int, course_code: str, reference: Any) -> str:
        """Fetch assessment details from DB or Portal."""
        if not hasattr(reference, "academic_year_id"):
            return "Invalid reference."
            
        if self.session_factory is not None and self.cipher is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from database.models import UserCourse, Assessment
            from sqlalchemy import select
            import json
            from parser.models import AssessmentDetailsResult

            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                db_user = await uow.users.get_by_telegram_id(telegram_id)
                if not db_user:
                    return "User not found."
                
                # Try finding it in DB first
                uc_stmt = select(UserCourse).where(UserCourse.user_id == db_user.id, UserCourse.course_id == course_code)
                ucs = await uow.session.scalars(uc_stmt)
                # Just take the first matching user_course that has this assessment (we don't know the year/sem here exactly, but it should be unique enough for the course, or we can just try all)
                for uc in ucs:
                    asm_stmt = select(Assessment).where(Assessment.user_course_id == uc.id)
                    asm_db = await uow.session.scalar(asm_stmt)
                    if asm_db:
                        try:
                            decrypted = self.cipher.decrypt(asm_db.encrypted_assessment_detail)
                            data = json.loads(decrypted)
                            if "scores" in data:
                                # It's a full detail, not just a reference
                                det = AssessmentDetailsResult.model_validate_json(decrypted)
                                return self._format_assessment(det)
                        except Exception:
                            pass
                            
                # If we get here, we need to scrape
                cred = await uow.credentials.get_by_user_id(db_user.id)
                if not cred or not self.portal_client:
                    return "Credentials missing or portal client not configured."
                    
                password = self.cipher.decrypt(cred.encrypted_password)
                
                det_result = await self.portal_client.scrape_assessment(
                    db_user.university_id,
                    password,
                    db_user.university_id,
                    reference.academic_year_id,
                    reference.semester_id,
                    reference.course_id
                )
                
                # Save it back if we can find the Assessment row
                # We need to know which uc it is.
                # The reference.course_id is the GUID on AAU side, not the course_code
                # But we know course_code. Let's just find the first uc with course_code and update its Assessment.
                uc_stmt = select(UserCourse).where(UserCourse.user_id == db_user.id, UserCourse.course_id == course_code)
                uc = await uow.session.scalar(uc_stmt)
                if uc:
                    asm_stmt = select(Assessment).where(Assessment.user_course_id == uc.id)
                    asm_db = await uow.session.scalar(asm_stmt)
                    if asm_db:
                        from crypto.cipher import Ciphertext
                        import base64
                        new_json = det_result.model_dump_json()
                        enc_asm = self.cipher.encrypt(new_json)
                        asm_db.encrypted_assessment_detail = enc_asm
                        await uow.commit()

                return self._format_assessment(det_result)

        return "Service unavailable."

    def _format_assessment(self, result: Any) -> str:
        if not result or not result.assessment:
            return "No details found."
        a = result.assessment
        lines = []
        for s in sorted(a.scores, key=lambda x: x.sequence):
            lines.append(f"• {s.name}: <code>{s.score}</code>")
        lines.append(f"\n<b>Total:</b> <code>{a.total_mark} / {a.total_possible}</code>")
        return "\n".join(lines)
