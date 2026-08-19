from pathlib import Path

import pytest

from clients.aau_portal import PortalDataValidationError, PortalSchemaChangedError
from parser.portal import parse_grade_report


def test_parses_grade_report_fixture():
    html = (Path("tests/fixtures/portal") / "grade_report.html").read_text(encoding="utf-8")
    results = parse_grade_report(html)

    assert len(results) == 2

    # Semester Two
    result1 = results[0]
    assert result1.academic_year == "2025/26"
    assert result1.year_label.lower() == "iii"
    assert result1.semester_label.lower() == "two"
    assert len(result1.course_grades) == 2

    row = result1.course_grades[0]
    assert row.course_name == "Advanced Software Engineering"
    assert row.course_code == "SE 301"
    assert row.credit_hours == 3.0
    assert row.ects == 5.0
    assert row.grade == "A"
    assert row.assessment.academic_year_id == "2025-26"
    assert row.assessment.semester_id == "2"
    assert row.assessment.course_id == "SE-301"

    assert result1.summary.sgp == 25.5
    assert result1.summary.sgpa == 3.64
    assert result1.summary.cgp == 150.0
    assert result1.summary.cgpa == 3.5
    assert result1.summary.academic_status == "Promoted"
    
    # Semester One
    result2 = results[1]
    assert result2.academic_year == "2025/26"
    assert result2.year_label.lower() == "iii"
    assert result2.semester_label.lower() == "one"
    assert len(result2.course_grades) == 1


def test_raises_for_missing_grade_table():
    with pytest.raises(PortalSchemaChangedError):
        parse_grade_report("<html><body>No table here</body></html>")


def test_raises_for_malformed_grade_row():
    html = "<table id='grade-report'><tbody><tr class='yrsm'><td>Academic Year : 2025/26, Year II, Semester : One</td></tr><tr><td>1</td><td>Example Course</td></tr><tr class='yrsm'><td>SGP : 15; SGPA : 3.0<br>CGP : 30; CGPA : 3.0<br>Academic Status : Promoted</td></tr></tbody></table>"
    with pytest.raises(PortalDataValidationError):
        parse_grade_report(html)

