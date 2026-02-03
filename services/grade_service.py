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

    async def get_stored_assessment(self, telegram_id: int, course_id: str) -> Optional[Assessment]:
        stmt = select(Assessment).where(
            Assessment.telegram_id == telegram_id,
            Assessment.course_id == course_id
        )
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
                assessment_data=assessment_data
            )
            self.db.add(new_assessment)
            has_changed = True
            message = f"🆕 New grade uploaded for {course_data['course_name']} ({course_id})!"
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
                if old_total != new_total:
                    message = f"🔄 Grade updated for {course_data['course_name']}: {old_total} ➡️ {new_total}"
                else:
                    message = f"📝 Assessment details updated for {course_data['course_name']}."

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
                sgpa=summary_data["sgpa"],
                cgpa=summary_data["cgpa"],
                status=summary_data["status"]
            )
            self.db.add(new_res)
            has_changed = True
            message = f"📊 Semester Results released! {summary_data['academic_year']} {summary_data['semester']}\nSGPA: {summary_data['sgpa']} | CGPA: {summary_data['cgpa']}\nStatus: {summary_data['status']}"
        else:
            if existing.sgpa != summary_data["sgpa"] or existing.cgpa != summary_data["cgpa"] or existing.status != summary_data["status"]:
                old_sgpa = existing.sgpa
                existing.sgpa = summary_data["sgpa"]
                existing.cgpa = summary_data["cgpa"]
                existing.status = summary_data["status"]
                existing.last_updated_at = datetime.utcnow()
                has_changed = True
                message = f"🔄 SGPA updated for {summary_data['academic_year']}: {old_sgpa} ➡️ {summary_data['sgpa']}"
        
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
                academic_year=course_data["academic_year"],
                semester=course_data["semester"],
                grade=new_grade_str
            )
            self.db.add(new_grade)
            # We only notify if the grade is actually something (not NG or empty)
            if new_grade_str and new_grade_str not in ["", "NG"]:
                has_changed = True
                message = f"🎓 Final grade released for **{course_data['course_name']}**: `{new_grade_str}`"
        else:
            if existing.grade != new_grade_str:
                old_grade = existing.grade
                existing.grade = new_grade_str
                existing.last_updated_at = datetime.utcnow()
                has_changed = True
                message = f"🔄 Final grade updated for **{course_data['course_name']}**: `{old_grade}` ➡️ `{new_grade_str}`"

        return has_changed, message

    async def get_year_results(self, telegram_id: int, academic_year: str = "All") -> Dict[str, Any]:
        """
        Retrieves all stored grades (Grade table) and semester summaries for a user.
        """
        from database.models import User, Grade
        # Get user
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await self.db.execute(stmt)).scalar_one_or_none()
        if not user:
            return {"grades": [], "summaries": []}

        # Final Grades
        grade_stmt = select(Grade).where(Grade.telegram_id == telegram_id)
        if academic_year != "All":
            grade_stmt = grade_stmt.where(Grade.academic_year.contains(academic_year))
        grades = (await self.db.execute(grade_stmt)).scalars().all()

        # Summaries
        summary_stmt = select(SemesterResult).where(SemesterResult.telegram_id == telegram_id)
        if academic_year != "All":
            summary_stmt = summary_stmt.where(SemesterResult.academic_year.contains(academic_year))
        summaries = (await self.db.execute(summary_stmt)).scalars().all()

        return {
            "grades": grades,
            "summaries": summaries
        }

    @staticmethod
    def format_grade_report(results: Dict[str, Any], title: str) -> str:
        """
        Formats results into a clean Telegram message.
        """
        grades = results["grades"]
        summaries = results["summaries"]

        if not grades and not summaries:
            return f"📭 No data found in database for **{title}**.\n\nPlease use the button below to fetch from the portal."

        msg = f"📊 **Grade Report: {title}**\n\n"

        # Group by Year/Semester
        grouped: Dict[str, List[Grade]] = {}
        for g in grades:
            key = f"{g.academic_year} - {g.semester}"
            grouped.setdefault(key, []).append(g)

        for period in sorted(grouped.keys()):
            msg += f"🗓 **{period}**\n"
            period_grades = grouped[period]
            for g in period_grades:
                grade_val = g.grade or "??"
                msg += f"• `{g.course_id}`: **{grade_val}**\n"
            
            # Find summary for this period
            # Period format: "Year X - Semester Y"
            period_summaries = [s for s in summaries if s.academic_year in period and s.semester in period]
            if period_summaries:
                s = period_summaries[0]
                msg += f"   └ SGPA: `{s.sgpa or 'N/A'}` | CGPA: `{s.cgpa or 'N/A'}`\n"
            msg += "\n"

        return msg
