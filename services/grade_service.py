from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Assessment, Course, SemesterResult, Grade
import hashlib
import json

class GradeService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    @staticmethod
    def get_assessment_hash(assessment_data: Dict[str, Any]) -> str:
        """
        Creates a deterministic hash of the assessment data to detect changes.
        """
        # Sort grades by name to ensure consistent hashing
        if "grades" in assessment_data:
            assessment_data["grades"] = sorted(assessment_data["grades"], key=lambda x: x["name"])
        
        data_str = json.dumps(assessment_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    @staticmethod
    def matches_year(item: Dict[str, Any], query: str) -> bool:
        """
        In-memory check if a parsed course/summary matches the year query.
        """
        if query == "All":
            return True
            
        full = (item.get("academic_year") or "").lower()
        level = (item.get("year_level") or "").lower()
        num = str(item.get("year_number") or "")
        
        q = query.lower().replace("year", "").strip()
        roman_map = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v"}
        roman = roman_map.get(q, q)
        
        return (
            q in full or 
            q in level or 
            roman in full or 
            roman in level or 
            (q.isdigit() and q == num)
        )

    async def get_stored_assessment(self, telegram_id: int, course_id: str) -> Optional[Assessment]:
        stmt = select(Assessment).where(
            Assessment.telegram_id == telegram_id,
            Assessment.course_id == course_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_assessment_by_id(self, assessment_id: int) -> Optional[Assessment]:
        stmt = select(Assessment).where(Assessment.id == assessment_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_course(self, course_data: Dict[str, Any]) -> Course:
        stmt = select(Course).where(
            Course.course_id == course_data["course_code"],
            Course.campus_id == course_data.get("campus_id", "CTBE"),
            Course.department_id == course_data.get("department_id", "SITE"),
            Course.academic_year == course_data["academic_year"],
            Course.semester == course_data["semester"]
        )
        result = await self.db.execute(stmt)
        course = result.scalar_one_or_none()
        
        if not course:
            course = Course(
                course_id=course_data["course_code"],
                course_name=course_data["course_name"],
                campus_id=course_data.get("campus_id", "CTBE"),
                department_id=course_data.get("department_id", "SITE"),
                academic_year=course_data["academic_year"],
                semester=course_data["semester"]
            )
            self.db.add(course)
            await self.db.flush()
        return course

    async def update_or_create_assessment(self, telegram_id: int, course_data: Dict[str, Any], assessment_data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Returns (has_changed, notification_message)
        """
        # Ensure course exists
        await self.get_or_create_course(course_data)
        
        course_id = course_data["course_code"]
        existing = await self.get_stored_assessment(telegram_id, course_id)
        
        has_changed = False
        message = ""

        if not existing:
            # New assessment detected
            new_assessment = Assessment(
                telegram_id=telegram_id,
                campus_id=course_data.get("campus_id", "CTBE"),
                department_id=course_data.get("department_id", "SITE"),
                course_id=course_id,
                academic_year=course_data["academic_year"],
                semester=course_data["semester"],
                year_level=course_data.get("year_level"),
                year_number=course_data.get("year_number"),
                assessment_data=assessment_data
            )
            self.db.add(new_assessment)
            has_changed = True
            name = self.escape_html(course_data['course_name'])
            message = f"🆕 New grade uploaded for <b>{name}</b> (<code>{course_id}</code>)!"
        else:
            # Check for changes
            old_hash = self.get_assessment_hash(existing.assessment_data)
            new_hash = self.get_assessment_hash(assessment_data)
            
            if old_hash != new_hash:
                old_total = existing.assessment_data.get("totalMark", "N/A")
                new_total = assessment_data.get("totalMark", "N/A")
                
                existing.assessment_data = assessment_data
                existing.last_updated_at = datetime.utcnow()
                
                has_changed = True
                name = self.escape_html(course_data['course_name'])
                if old_total != new_total:
                    message = f"🔄 Grade updated for <b>{name}</b>: <code>{old_total}</code> ➡️ <code>{new_total}</code>"
                else:
                    message = f"📝 Assessment details updated for <b>{name}</b>."

        return has_changed, message

    async def update_or_create_semester_result(self, telegram_id: int, summary_data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Returns (has_changed, notification_message)
        """
        stmt = select(SemesterResult).where(
            SemesterResult.telegram_id == telegram_id,
            SemesterResult.academic_year == summary_data["academic_year"],
            SemesterResult.semester == summary_data["semester"]
        )
        res = await self.db.execute(stmt)
        existing = res.scalar_one_or_none()
        
        has_changed = False
        message = ""
        
        if not existing:
            new_res = SemesterResult(
                telegram_id=telegram_id,
                academic_year=summary_data["academic_year"],
                semester=summary_data["semester"],
                year_level=summary_data.get("year_level"),
                year_number=summary_data.get("year_number"),
                sgpa=summary_data["sgpa"],
                cgpa=summary_data["cgpa"],
                status=summary_data["status"]
            )
            self.db.add(new_res)
            has_changed = True
            yr = self.escape_html(summary_data['academic_year'])
            sem = self.escape_html(summary_data['semester'])
            message = f"📊 Semester Results released! <b>{yr} {sem}</b>\nSGPA: <code>{summary_data['sgpa']}</code> | CGPA: <code>{summary_data['cgpa']}</code>\nStatus: <i>{summary_data['status']}</i>"
        else:
            if existing.sgpa != summary_data["sgpa"] or existing.cgpa != summary_data["cgpa"] or existing.status != summary_data["status"]:
                old_sgpa = existing.sgpa
                existing.sgpa = summary_data["sgpa"]
                existing.cgpa = summary_data["cgpa"]
                existing.status = summary_data["status"]
                existing.last_updated_at = datetime.utcnow()
                has_changed = True
                yr = self.escape_html(summary_data['academic_year'])
                message = f"🔄 SGPA updated for <b>{yr}</b>: <code>{old_sgpa}</code> ➡️ <code>{summary_data['sgpa']}</code>"
        
        return has_changed, message
    async def update_or_create_grade(self, telegram_id: int, course_data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Detects changes in the final grade letter (A, B, etc.)
        Returns (has_changed, notification_message)
        """
        # Ensure course exists in global registry
        await self.get_or_create_course(course_data)
        
        course_id = course_data["course_code"]
        stmt = select(Grade).where(
            Grade.telegram_id == telegram_id,
            Grade.course_id == course_id,
            Grade.academic_year == course_data["academic_year"],
            Grade.semester == course_data["semester"]
        )
        res = await self.db.execute(stmt)
        existing = res.scalar_one_or_none()
        
        has_changed = False
        message = ""
        new_grade_str = course_data.get("grade", "N/A")

        if not existing:
            new_grade = Grade(
                telegram_id=telegram_id,
                campus_id=course_data.get("campus_id", "CTBE"),
                department_id=course_data.get("department_id", "SITE"),
                course_id=course_id,
                course_name=course_data.get("course_name"),
                academic_year=course_data["academic_year"],
                semester=course_data["semester"],
                year_level=course_data.get("year_level"),
                year_number=course_data.get("year_number"),
                grade=new_grade_str,
                credit_hour=course_data.get("credit_hour"),
                ects=course_data.get("ects")
            )
            self.db.add(new_grade)
                # We only notify if the grade is actually something (not NG or empty)
            if new_grade_str and new_grade_str not in ["", "NG"]:
                has_changed = True
                name = self.escape_html(course_data['course_name'])
                message = f"🎓 Final grade released for <b>{name}</b>: <code>{new_grade_str}</code>"
        else:
            if existing.grade != new_grade_str:
                old_grade = existing.grade
                existing.grade = new_grade_str
                existing.last_updated_at = datetime.utcnow()
                has_changed = True
                name = self.escape_html(course_data['course_name'])
                message = f"🔄 Final grade updated for <b>{name}</b>: <code>{old_grade}</code> ➡️ <code>{new_grade_str}</code>"

        return has_changed, message

    async def get_year_results(self, telegram_id: int, year_query: str = "All") -> Dict[str, Any]:
        """
        Retrieves all stored grades and semester summaries for a user with flexible year matching.
        """
        # Final Grades
        grade_stmt = select(Grade).where(Grade.telegram_id == telegram_id)
        
        if year_query != "All":
            # Flexible matching for "Year 3", "3", "III", etc.
            normalized = year_query.lower().replace("year", "").strip()
            roman_map = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V"}
            roman = roman_map.get(normalized, normalized.upper())
            
            grade_stmt = grade_stmt.where(
                (Grade.academic_year.ilike(f"%{year_query}%")) |
                (Grade.year_level.ilike(f"%{year_query}%")) |
                (Grade.year_level.ilike(f"%{roman}%"))
            )
            
            if normalized.isdigit():
                grade_stmt = grade_stmt.where(Grade.year_number == int(normalized))

        grades = (await self.db.execute(grade_stmt)).scalars().all()

        # Summaries
        summary_stmt = select(SemesterResult).where(SemesterResult.telegram_id == telegram_id)
        if year_query != "All":
            # We don't have year_number in SemesterResult yet, but we can match by string
            summary_stmt = summary_stmt.where(SemesterResult.academic_year.ilike(f"%{year_query}%"))
            
        summaries = (await self.db.execute(summary_stmt)).scalars().all()

        return {
            "grades": grades,
            "summaries": summaries
        }

    async def get_assessments_for_grades(self, telegram_id: int, grades: List[Grade]) -> Dict[str, Assessment]:
        """
        Fetches matching assessments for a list of grades.
        """
        results = {}
        for g in grades:
            # Look up assessment by course code and period
            stmt = select(Assessment).where(
                Assessment.telegram_id == telegram_id,
                Assessment.course_id == g.course_id,
                Assessment.academic_year == g.academic_year,
                Assessment.semester == g.semester
            )
            res = await self.db.execute(stmt)
            assessment = res.scalar_one_or_none()
            if assessment:
                results[str(g.id)] = assessment
        return results

    @staticmethod
    def format_grade_report(results: Dict[str, Any], title: str) -> List[Dict[str, Any]]:
        """
        Formats results into structured data for the handler to send.
        Returns a list of chunks (one per semester) to avoid Telegram message limits.
        """
        grades = results["grades"]
        summaries = results["summaries"]

        if not grades and not summaries:
            t = self.escape_html(title)
            return [{
                "text": f"📭 No results found for <b>{t}</b>.\n\nThis could mean:\n• Results haven't been released yet\n• You haven't reached that year level\n• Try checking 'All' years.",
                "kb_data": None
            }]

        chunks = []
        
        # Group by Year/Semester
        grouped: Dict[str, List[Grade]] = {}
        for g in grades:
            key = f"{g.year_level or g.academic_year} - {g.semester}"
            grouped.setdefault(key, []).append(g)

        # Sort keys reliably? Ideally by year/semester order.
        # For now alphabetical but Year I < Year II
        sorted_keys = sorted(grouped.keys())

        for period in sorted_keys:
            p = self.escape_html(period)
            msg = f"📚 <b>{p}</b>\n\n"
            period_grades = grouped[period]
            
            buttons = []
            for idx, g in enumerate(period_grades, 1):
                emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][idx-1] if idx <= 10 else "🔹"
                grade_val = g.grade if g.grade and g.grade != "NG" else "Pending"
                
                name = self.escape_html(g.course_name or g.course_id)
                msg += f"{emoji} <b>{name}</b>\n"
                msg += f"   Code: <code>{g.course_id}</code> | Grade: <b>{grade_val}</b>\n\n"
                
                buttons.append({"text": f"📊 {g.course_id}", "callback_data": f"view_asms_{g.id}"})

            # Check for summary
            summary = next((s for s in summaries if s.academic_year in period or s.semester in period), None)
            if summary:
                msg += f"📈 <b>Summary</b>\n"
                msg += f"SGPA: <code>{summary.sgpa or '0.00'}</code> | CGPA: <code>{summary.cgpa or '0.00'}</code>\n"
                msg += f"Status: <i>{self.escape_html(summary.status or 'N/A')}</i>\n"

            chunks.append({
                "text": msg,
                "buttons": buttons
            })

        return chunks

    def format_assessment_detail(self, grade: Grade, assessment: Assessment) -> str:
        """
        Formats assessment breakdown for a course.
        """
        name = self.escape_html(grade.course_name or grade.course_id)
        msg = f"📊 <b>{name}</b>\n"
        msg += f"Code: <code>{grade.course_id}</code>\n"
        msg += f"Final Grade: <b>{grade.grade or 'N/A'}</b>\n\n"
        
        msg += "📝 <b>Assessment Breakdown:</b>\n"
        data = assessment.assessment_data
        
        grades = data.get("grades", [])
        if not grades:
            msg += "   <i>No breakdown available</i>\n"
        else:
            for g in grades:
                msg += f"• {self.escape_html(g['name'])} ({g.get('weight', '??')}): <b>{g['result']}</b>\n"
        
        total = data.get("totalMark", "N/A")
        msg += f"\n✅ <b>Total:</b> <code>{total}</code>"
        
        return msg

    def escape_html(self, text: str) -> str:
        """Simple HTML escaping for safety"""
        if not text: return ""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
