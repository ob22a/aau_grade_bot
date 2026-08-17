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
        f"🎓 *AAU Grade Report*",
        f"📅 *Academic Year:* {academic_year} | *Year:* {year_label}",
        f"📘 *Semester:* {semester_label}",
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

            lines.append(f"📚 *{code} {name}*".strip())
            lines.append(f"  • Credits: {credits} | ECTS: {ects} | Grade: *{grade}*")

            # Inline Detailed Assessment Breakdown
            assessments = course.get("assessments", [])
            if assessments:
                lines.append("  📊 *Assessment Breakdown:*")
                for item in assessments:
                    score_name = item.get("name", "Assessment")
                    score_val = item.get("score", 0.0)
                    lines.append(f"    - {score_name}: `{score_val}`")
                total = course.get("total_mark")
                if total is not None:
                    lines.append(f"    - *Total Mark:* `{total}%`")
            lines.append("")

    if summary:
        sgp = summary.get("sgp", 0.0)
        sgpa = summary.get("sgpa", 0.0)
        cgpa = summary.get("cgpa", 0.0)
        status = summary.get("academic_status", "Active")
        lines.append("──────────────────────────────")
        lines.append(f"📊 *Summary:* SGPA: `{sgpa:.2f}` | CGPA: `{cgpa:.2f}`")
        lines.append(f"Status: *{status}*")

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
            pages.append(
                format_grade_report_page(
                    academic_year=getattr(rep, "academic_year", "N/A"),
                    semester_label=getattr(rep, "semester_label", "N/A"),
                    year_label=getattr(rep, "year_label", "N/A"),
                    course_grades=course_dicts,
                    summary=summary_dict,
                )
            )
        return pages

    async def read(self, request: GradeReadRequest) -> GradeReadResult:
        cache_key = f"grades:{request.telegram_id}"
        cooldown_key = f"cooldown:scrape:{request.telegram_id}"

        # 1. Try cache if available and not forced refresh
        if self.cache is not None and not request.force_refresh:
            cached_val = await self.cache.get(cache_key)
            if cached_val is not None:
                try:
                    pages = json.loads(cached_val)
                    if isinstance(pages, list) and pages:
                        # Crude filter for cached HTML strings
                        filtered_pages = []
                        for p in pages:
                            if request.year_filter and request.year_filter != "All" and request.year_filter not in p:
                                continue
                            if request.semester_filter and request.semester_filter != "All" and request.semester_filter not in p:
                                continue
                            filtered_pages.append(p)
                        
                        if not filtered_pages:
                            filtered_pages = pages # Fallback if filter too strict
                            
                        idx = max(0, min(request.page_index, len(filtered_pages) - 1))
                        return GradeReadResult(
                            message=filtered_pages[idx],
                            cached=True,
                            current_page=idx,
                            total_pages=len(filtered_pages),
                        )
                except Exception:
                    return GradeReadResult(message=str(cached_val), cached=True)

        # 1b. Check scrape cooldown if force_refresh
        if self.cache is not None and request.force_refresh:
            if await self.cache.get(cooldown_key):
                # Still in cooldown, fallback to cached grades and add warning
                cached_val = await self.cache.get(cache_key)
                if cached_val is not None:
                    try:
                        pages = json.loads(cached_val)
                        if isinstance(pages, list) and pages:
                            idx = max(0, min(request.page_index, len(pages) - 1))
                            return GradeReadResult(
                                message=f"⏳ <b>Cooldown Active</b>\nYou can only refresh from the portal every {self.manual_scrape_cooldown_minutes} minutes to reduce load. Showing cached grades.\n\n{pages[idx]}",
                                cached=True,
                                current_page=idx,
                                total_pages=len(pages),
                            )
                    except Exception:
                        pass
                return GradeReadResult(
                    message=f"⏳ <b>Cooldown Active</b>\nYou can only refresh from the portal every {self.manual_scrape_cooldown_minutes} minutes. Cached grades are currently unavailable.",
                    cached=True,
                )

        # 2. Try DB and live portal scrape if credentials exist
        if self.session_factory is not None and self.cipher is not None and self.portal_client is not None:
            try:
                from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
                async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                    db_user = await uow.users.get_by_telegram_id(request.telegram_id)
                    if db_user is not None and db_user.id:
                        cred = await uow.credentials.get_by_user_id(db_user.id)
                        if cred is not None:
                            try:
                                password = self.cipher.decrypt(cred.encrypted_password)
                                _profile, grade_reports = await self.portal_client.scrape(
                                    db_user.university_id,
                                    password,
                                    db_user.university_id,
                                )
                                pages = self._format_reports_to_pages(grade_reports, request.year_filter, request.semester_filter)
                                if pages:
                                    if self.cache is not None:
                                        await self.cache.set(cache_key, json.dumps(pages), ttl_seconds=1800)
                                        await self.cache.set(cooldown_key, "1", ttl_seconds=self.manual_scrape_cooldown_minutes * 60)
                                    idx = max(0, min(request.page_index, len(pages) - 1))
                                    return GradeReadResult(
                                        message=pages[idx],
                                        cached=False,
                                        current_page=idx,
                                        total_pages=len(pages),
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

