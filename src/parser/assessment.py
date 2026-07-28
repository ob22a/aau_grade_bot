"""AAU assessment detail modal HTML parser with safe error handling."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.clients.aau_portal import PortalSchemaChangedError, PortalDataValidationError, SchemaChangeDiagnostic
from .models import AssessmentDetailsResult, AssessmentDetails, AssessmentScore


def parse_assessment_details(html: str) -> AssessmentDetailsResult:
    """
    Parse AAU assessment modal HTML and extract assessment score breakdown.

    Extracts:
    - Course Name
    - Individual assessment components with scores
    - Total mark and possible mark

    Args:
        html: Raw HTML of assessment modal containing score details

    Returns:
        AssessmentDetailsResult with AssessmentDetails frozen DTO

    Raises:
        PortalSchemaChangedError: If expected modal table structure missing
        PortalDataValidationError: If assessment data cannot be parsed
    """
    soup = BeautifulSoup(html, "html.parser")
    warnings = []

    # Find the modal table containing assessment data
    modal_table = soup.find("table", class_=re.compile(r"table.*bordered.*striped"))
    if not modal_table:
        diagnostic = SchemaChangeDiagnostic(
            page_type="assessment",
            detected_element="modal table",
            expected_selector="table.table.table-bordered.table-striped",
            detail="Assessment modal table not found"
        )
        raise PortalSchemaChangedError(
            f"Assessment modal table not found. {diagnostic.detail}",
            diagnostic
        )

    tbody = modal_table.find("tbody")
    if not tbody:
        diagnostic = SchemaChangeDiagnostic(
            page_type="assessment",
            detected_element="table body",
            expected_selector="tbody inside modal table",
            detail="Assessment table body missing"
        )
        raise PortalSchemaChangedError(
            f"Assessment table body not found. {diagnostic.detail}",
            diagnostic
        )

    rows = tbody.find_all("tr")
    if not rows:
        raise PortalDataValidationError("No rows found in assessment table")

    # First row should contain course name (typically in a colspan header)
    course_name_row = rows[0]
    course_name_cells = course_name_row.find_all(["td", "th"])  # Can be either td or th

    if not course_name_cells:
        raise PortalDataValidationError("Could not find course name in assessment table")

    # Extract course name from first cell (format usually "Course : Course Name")
    course_cell_text = course_name_cells[0].get_text(strip=True)
    match = re.search(r"Course\s*:\s*(.+?)(?:_r)?$", course_cell_text, re.IGNORECASE)

    if not match:
        raise PortalDataValidationError(f"Could not parse course name from: {course_cell_text}")

    course_name = match.group(1).strip()

    # Skip header row and accumulate assessment rows
    scores = []
    total_mark = None
    total_possible = None

    for row in rows[1:]:
        cells = row.find_all(["td", "th"])  # Can be either td or th

        # Check if this is a total row (has "Total Mark" in first cell)
        if cells and "Total Mark" in cells[0].get_text():
            # Extract "Total Mark : 98 / 100" format
            total_text = cells[0].get_text(strip=True)
            match = re.search(r"Total Mark\s*:\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", total_text, re.IGNORECASE)

            if match:
                try:
                    total_mark = float(match.group(1))
                    total_possible = float(match.group(2))
                except ValueError:
                    pass
            continue

        # Skip header rows (contains S.No., Assessment, Result or similar column headers)
        # Header rows typically have cells like "S.No.", "Assessment", "Result"
        if cells and all(cell.name == "th" for cell in cells):
            first_cell_text = cells[0].get_text(strip=True).lower()
            if "s.no" in first_cell_text or "s.n" in first_cell_text or "no." in first_cell_text:
                continue

        # Regular assessment row should have 3 cells: S.No, Assessment, Result
        if len(cells) >= 3:
            try:
                sequence = int(cells[0].get_text(strip=True))
                name = cells[1].get_text(strip=True)
                score = float(cells[2].get_text(strip=True))

                scores.append(AssessmentScore(sequence=sequence, name=name, score=score))
            except (ValueError, IndexError) as exc:
                raise PortalDataValidationError(
                    f"Failed to parse assessment row: {exc}"
                ) from exc

    if not scores:
        raise PortalDataValidationError("No assessment scores found in modal")

    if total_mark is None or total_possible is None:
        raise PortalDataValidationError("Could not find total mark in assessment modal")

    # Create assessment DTO
    try:
        assessment = AssessmentDetails(
            course_name=course_name,
            scores=tuple(scores),
            total_mark=total_mark,
            total_possible=total_possible
        )
    except Exception as exc:
        raise PortalDataValidationError(
            f"Failed to construct AssessmentDetails: {exc}"
        ) from exc

    return AssessmentDetailsResult(
        assessment=assessment,
        warnings=tuple(warnings)
    )

