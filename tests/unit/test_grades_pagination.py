"""Unit tests for grade formatting and pagination handlers."""

from __future__ import annotations

from services.grades.service import format_grade_report_page
from handlers.commands.grades import build_grades_keyboard


def test_format_grade_report_page_with_assessments() -> None:
    course_grades = [
        {
            "course_code": "SECT-3082",
            "course_name": "Software Engineering II",
            "credit_hours": 3,
            "ects": 5,
            "grade": "A",
            "total_mark": 88.5,
            "assessments": [
                {"name": "Quiz 1", "score": 9.5},
                {"name": "Midterm Exam", "score": 27.0},
                {"name": "Final Exam", "score": 44.0},
            ],
        }
    ]
    summary = {
        "sgp": 38.0,
        "sgpa": 4.0,
        "cgpa": 3.92,
        "academic_status": "PROMOTED",
    }

    formatted = format_grade_report_page(
        academic_year="2023/2024",
        semester_label="First Semester",
        year_label="Year III",
        course_grades=course_grades,
        summary=summary,
    )

    assert "SECT-3082 Software Engineering II" in formatted
    assert "Credits: 3 | ECTS: 5 | Grade: <b>A</b>" in formatted
    assert "Assessment Breakdown:" not in formatted
    assert "Total Mark:" not in formatted
    assert "SGPA: <code>4.00</code> | CGPA: <code>3.92</code>" in formatted


from parser.models import GradeReport, GradeReportSummary, CourseGrade, AssessmentReference
def test_build_grades_keyboard_courses() -> None:
    # Test keyboard with course inline buttons
    report = GradeReport(
        warnings=(),
        academic_year="2025/26",
        year_label="Year 1",
        semester_label="Semester One",
        course_grades=(
            CourseGrade(
                course_number=1,
                course_name="Course 1",
                course_code="C1",
                credit_hours=3,
                ects=5,
                grade="A",
                assessment=AssessmentReference(academic_year_id="1", semester_id="1", course_id="1")
            ),
        ),
        summary=GradeReportSummary(sgp=0, sgpa=0, cgp=0, cgpa=0, academic_status="")
    )
    keyboard = build_grades_keyboard(year="2025/26", semester="One", report=report)
    assert len(keyboard.inline_keyboard) == 3
    assert keyboard.inline_keyboard[0][0].callback_data == "grade_c:2025/26:One:0"
    assert keyboard.inline_keyboard[1][0].callback_data == "grade_r:2025/26:One"
    assert keyboard.inline_keyboard[2][0].callback_data == "view_grades_filter"
