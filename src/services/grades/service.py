"""Cached and formatted grade read service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from dto.bot import GradeReadRequest, GradeReadResult
from parser.models import GradeReport, CourseGrade, AssessmentReference, GradeReportSummary


@dataclass(frozen=True)
class CachedGradeSnapshot:
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
        filtered_reports = []
        for rep in reports_list:
            rep_year = getattr(rep, "year_label", "N/A")
            rep_sem = getattr(rep, "semester_label", "N/A")
            
            if year_filter and year_filter != "All":
                # Ensure year matches (e.g. "Year 1" matches "Year : 1" or "Year 1")
                # User's year_filter might be "Year 1", so we can just check if "1" is in both
                import re
                yf_match = re.search(r'\d+', year_filter)
                ry_match = re.search(r'\d+', rep_year)
                if yf_match and ry_match and yf_match.group() != ry_match.group():
                    continue
            
            if semester_filter and semester_filter != "All":
                # Ensure semester matches
                sf_lower = semester_filter.lower()
                rf_lower = rep_sem.lower()
                if "one" in sf_lower and "one" not in rf_lower and "1" not in rf_lower and "i" not in rf_lower:
                    continue
                if "two" in sf_lower and "two" not in rf_lower and "2" not in rf_lower and "ii" not in rf_lower:
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
                        else:
                            # Force refresh from portal
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
                                    from database.models import Semester
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
                                    from clients.aau_portal import PortalSchemaChangedError
                                    if isinstance(scrape_err, PortalSchemaChangedError) and self.notification_service is not None:
                                        snippet = getattr(scrape_err.diagnostic, "html_snippet", "")
                                        await self.notification_service.send_admin_alert(
                                            f"Portal schema changed during grades refresh: {scrape_err}",
                                            snippet
                                        )
                                    logging.getLogger(__name__).warning(f"Portal scrape failed for user: {scrape_err}")
            except Exception as db_err:
                import logging
                logging.getLogger(__name__).warning(f"DB user query failed: {db_err}")

        # 3. Check repository if provided
        if self.repository is not None:
            stored = await self.repository.get_by_user_id(str(request.telegram_id))
            if stored is not None:
                message = getattr(stored, "message", "Grades retrieved")
                if self.cache is not None:
                    await self.cache.set(cache_key, message, ttl_seconds=1800)
                return GradeReadResult(
                    message=message,
                    cached=False,
                    current_page=0,
                    total_pages=1,
                )

        # 4. Default fallback message if no grades exist yet
        return GradeReadResult(
            message=(
                "No grades available yet. Please use /register to connect your AAU account "
                "or refresh your grades."
            ),
            cached=False,
            current_page=0,
            total_pages=1,
        )

