from pathlib import Path

import pytest

from clients.aau_portal import PortalDataValidationError, PortalSchemaChangedError
from parser.portal import parse_grade_report


def test_parses_grade_report_fixture():
    html = (Path("tests/fixtures/portal") / "grade_report.html").read_text(encoding="utf-8")
    result = parse_grade_report(html)

    assert result.academic_year == "2025/26"
    assert result.year_label.lower() == "ii"
    assert result.semester_label.lower() == "one"
    assert len(result.course_grades) == 1

    row = result.course_grades[0]
    assert row.course_name == "Example Course"
    assert row.course_code == "EX 2001"
    assert row.credit_hours == 3.0
    assert row.ects == 5.0
    assert row.grade == "A"
    assert row.assessment.academic_year_id == "YEAR-ID"
    assert row.assessment.semester_id == "SEMESTER-ID"
    assert row.assessment.course_id == "COURSE-ID"

    assert result.summary.sgp == 15.0
    assert result.summary.sgpa == 3.0
    assert result.summary.cgp == 30.0
    assert result.summary.cgpa == 3.0
    assert result.summary.academic_status == "Promoted"


def test_raises_for_missing_grade_table():
    with pytest.raises(PortalSchemaChangedError):
        parse_grade_report("<html><body>No table here</body></html>")


def test_raises_for_malformed_grade_row():
    html = "<table id='grade-report'><tbody><tr class='yrsm'><td>Academic Year : 2025/26, Year II, Semester : One</td></tr><tr><td>1</td><td>Example Course</td></tr><tr class='yrsm'><td>SGP : 15; SGPA : 3.0<br>CGP : 30; CGPA : 3.0<br>Academic Status : Promoted</td></tr></tbody></table>"
    with pytest.raises(PortalDataValidationError):
        parse_grade_report(html)
