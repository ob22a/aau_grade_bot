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
    assert "Credits: 3 | ECTS: 5 | Grade: *A*" in formatted
    assert "Assessment Breakdown:" in formatted
    assert "Quiz 1: `9.5`" in formatted
    assert "Midterm Exam: `27.0`" in formatted
    assert "Final Exam: `44.0`" in formatted
    assert "Total Mark:* `88.5%`" in formatted
    assert "SGPA: `4.00` | CGPA: `3.92`" in formatted


def test_build_grades_keyboard_pagination() -> None:
    # Test single page keyboard (has nav indicator row + refresh row)
    keyboard_single = build_grades_keyboard(current_page=0, total_pages=1)
    assert len(keyboard_single.inline_keyboard) == 2
    assert keyboard_single.inline_keyboard[0][0].callback_data == "grade_noop"
    assert keyboard_single.inline_keyboard[1][0].callback_data == "grade_refresh"

    # Test multi-page keyboard (middle page)
    keyboard_multi = build_grades_keyboard(current_page=1, total_pages=3)
    assert len(keyboard_multi.inline_keyboard) == 2
    row0 = keyboard_multi.inline_keyboard[0]
    assert len(row0) == 3
    assert row0[0].callback_data == "grade_page:0"
    assert row0[1].callback_data == "grade_noop"
    assert row0[2].callback_data == "grade_page:2"
