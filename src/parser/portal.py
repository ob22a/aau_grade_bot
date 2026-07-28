from __future__ import annotations

import re
from typing import Iterable

from bs4 import BeautifulSoup

from parser.errors import PortalDataValidationError, PortalSchemaChangedError, SchemaChangeDiagnostic
from parser.models import AssessmentReference, CourseGrade, GradeReport, GradeReportSummary


_TERM_PATTERN = re.compile(
    r"Academic Year\s*:\s*(?P<academic_year>[^,]+),\s*Year\s*(?P<year_label>[^,]+),\s*Semester\s*:\s*(?P<semester_label>.+)",
    re.IGNORECASE,
)
_ASSESSMENT_PATTERN = re.compile(
    r"modalButtonClicked\(\s*'(?P<academic_year_id>[^']+)'\s*,\s*'(?P<semester_id>[^']+)'\s*,\s*'(?P<course_id>[^']+)'\s*\)",
)


def _grade_row_cells(row: BeautifulSoup) -> list[str]:
    return [cell.get_text(" ", strip=True) for cell in row.find_all("td")]


def _parse_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise PortalDataValidationError(f"Invalid float for {field_name}: {value}") from exc


def _parse_term_row(term_row: BeautifulSoup) -> tuple[str, str, str]:
    text = term_row.get_text(" ", strip=True)
    match = _TERM_PATTERN.search(text)
    if not match:
        raise PortalSchemaChangedError(
            SchemaChangeDiagnostic(
                page_kind="grade_report",
                expected="Academic Year : <year>, Year <label>, Semester : <label>",
                observed_structure_fingerprint=text[:200],
            )
        )
    return (
        match.group("academic_year").strip(),
        match.group("year_label").strip(),
        match.group("semester_label").strip(),
    )


def _parse_course_row(row: BeautifulSoup) -> CourseGrade:
    cells = row.find_all("td")
    if len(cells) < 7:
        raise PortalDataValidationError("Grade row has unexpected column count")

    onclick_button = row.select_one("button[onclick]")
    if onclick_button is None:
        raise PortalDataValidationError("Missing assessment callback on grade row")

    assessment_match = _ASSESSMENT_PATTERN.search(onclick_button["onclick"])
    if not assessment_match:
        raise PortalDataValidationError("Assessment callback does not contain expected parameters")

    assessment = AssessmentReference(
        academic_year_id=assessment_match.group("academic_year_id"),
        semester_id=assessment_match.group("semester_id"),
        course_id=assessment_match.group("course_id"),
    )

    return CourseGrade(
        course_number=int(cells[0].get_text(" ", strip=True)),
        course_name=cells[1].get_text(" ", strip=True),
        course_code=cells[2].get_text(" ", strip=True),
        credit_hours=_parse_float(cells[3].get_text(" ", strip=True), "credit_hours"),
        ects=_parse_float(cells[4].get_text(" ", strip=True), "ects"),
        grade=cells[5].get_text(" ", strip=True),
        assessment=assessment,
    )


def _parse_summary_row(summary_row: BeautifulSoup) -> GradeReportSummary:
    text = summary_row.get_text(" ", strip=True)
    if "SGP" not in text:
        raise PortalSchemaChangedError(
            SchemaChangeDiagnostic(
                page_kind="grade_report",
                expected="Summary row with SGP, SGPA, CGP, CGPA, Academic Status",
                observed_structure_fingerprint=text[:200],
            )
        )

    try:
        sgp = float(re.search(r"SGP\s*:\s*([\d.]+)", text).group(1))
        sgpa = float(re.search(r"SGPA\s*:\s*([\d.]+)", text).group(1))
        cgp = float(re.search(r"CGP\s*:\s*([\d.]+)", text).group(1))
        cgpa = float(re.search(r"CGPA\s*:\s*([\d.]+)", text).group(1))
        status_match = re.search(r"Academic Status\s*:\s*([^;]+)$", text)
        academic_status = status_match.group(1).strip() if status_match else ""
    except AttributeError as exc:
        raise PortalDataValidationError("Grade summary row is malformed") from exc

    return GradeReportSummary(
        sgp=sgp,
        sgpa=sgpa,
        cgp=cgp,
        cgpa=cgpa,
        academic_status=academic_status,
    )


def _find_grade_rows(rows: Iterable[BeautifulSoup]) -> list[BeautifulSoup]:
    return [row for row in rows if "yrsm" not in row.get("class", [])]


def parse_grade_report(html: str) -> GradeReport:
    document = BeautifulSoup(html, "html.parser")
    table = document.select_one("table#grade-report")
    if table is None:
        raise PortalSchemaChangedError(
            SchemaChangeDiagnostic(
                page_kind="grade_report",
                expected="HTML table with id 'grade-report'",
                observed_structure_fingerprint=html[:200],
            )
        )

    rows = table.select("tbody > tr")
    if len(rows) < 3:
        raise PortalDataValidationError("Grade report contains too few rows")

    term_row = rows[0]
    summary_row = rows[-1]
    course_rows = _find_grade_rows(rows[1:-1])

    if not course_rows:
        raise PortalDataValidationError("No course rows found in grade report")

    academic_year, year_label, semester_label = _parse_term_row(term_row)
    course_grades = tuple(_parse_course_row(row) for row in course_rows)
    summary = _parse_summary_row(summary_row)

    return GradeReport(
        academic_year=academic_year,
        year_label=year_label,
        semester_label=semester_label,
        course_grades=course_grades,
        summary=summary,
    )
