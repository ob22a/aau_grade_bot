"""AAU home page HTML parser with safe error handling for profile extraction."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from src.clients.aau_portal import PortalSchemaChangedError, PortalDataValidationError, SchemaChangeDiagnostic
from .models import ParserWarning, ParserWarningCode, ProfilePageResult, StudentProfileData

if TYPE_CHECKING:
    pass


def parse_profile_page(html: str) -> ProfilePageResult:
    """
    Parse AAU home page HTML and extract student profile information.

    Extracts:
    - Full Name
    - Student ID
    - Department
    - Year Level (e.g., "Year III")
    - Campus (optional)
    - Section (optional)

    Args:
        html: Raw HTML of home page containing profile section

    Returns:
        ProfilePageResult with StudentProfileData frozen DTO

    Raises:
        PortalSchemaChangedError: If expected profile table structure missing
        PortalDataValidationError: If critical profile fields cannot be parsed
    """
    soup = BeautifulSoup(html, "html.parser")
    warnings = []

    # Find the profile widget section by looking for the heading "My Profile"
    profile_heading = soup.find(string=re.compile(r"My Profile", re.IGNORECASE))
    if not profile_heading:
        diagnostic = SchemaChangeDiagnostic(
            page_type="home",
            detected_element="profile heading",
            expected_selector="span with text 'My Profile'",
            detail="Profile section not found on home page"
        )
        raise PortalSchemaChangedError(
            f"Home page profile heading not found. {diagnostic.detail}",
            diagnostic
        )

    # Find the parent widget containing the profile table
    profile_widget = profile_heading.find_parent("div", class_="widget")
    if not profile_widget:
        diagnostic = SchemaChangeDiagnostic(
            page_type="home",
            detected_element="profile widget",
            expected_selector="div.widget containing profile heading",
            detail="Profile widget container not found"
        )
        raise PortalSchemaChangedError(
            f"Could not locate profile widget. {diagnostic.detail}",
            diagnostic
        )

    # Find the profile table within the widget
    profile_table = profile_widget.find("table")
    if not profile_table:
        diagnostic = SchemaChangeDiagnostic(
            page_type="home",
            detected_element="profile table",
            expected_selector="table inside profile widget",
            detail="No table found in profile section"
        )
        raise PortalSchemaChangedError(
            f"Profile table not found. {diagnostic.detail}",
            diagnostic
        )

    # Extract profile data from table rows
    rows = profile_table.find_all("tr")
    profile_data = {}

    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 2:
            label_cell = cells[0].get_text(strip=True)
            value_cell = cells[1].get_text(strip=True)

            if not value_cell:  # Skip empty rows or spacing rows
                continue

            # Map labels to data keys (case-insensitive)
            if "Full Name" in label_cell or "Name" in label_cell:
                profile_data["full_name"] = value_cell
            elif "ID No" in label_cell or "Student ID" in label_cell:
                profile_data["student_id"] = value_cell
            elif "Department" in label_cell:
                profile_data["department"] = value_cell
            elif "Year" in label_cell:
                profile_data["year_level"] = value_cell
            elif "Campus" in label_cell:
                profile_data["campus"] = value_cell
            elif "Section" in label_cell:
                profile_data["section"] = value_cell

    # Validate critical fields
    critical_fields = ["full_name", "student_id", "department", "year_level"]
    missing_critical = [f for f in critical_fields if f not in profile_data]

    if missing_critical:
        raise PortalDataValidationError(
            f"Missing critical profile fields: {missing_critical}"
        )

    # Check for optional fields and warn if missing
    optional_fields = ["campus", "section"]
    for field in optional_fields:
        if field not in profile_data:
            warnings.append(
                ParserWarning(
                    code=ParserWarningCode.MISSING_OPTIONAL_PROFILE_FIELD,
                    page_kind="home",
                    detail=f"Optional field '{field}' not found in profile table"
                )
            )
            profile_data[field] = None

    # Create profile DTO
    try:
        profile = StudentProfileData(
            full_name=profile_data["full_name"],
            student_id=profile_data["student_id"],
            department=profile_data["department"],
            year_level=profile_data["year_level"],
            campus=profile_data.get("campus"),
            section=profile_data.get("section")
        )
    except Exception as exc:
        raise PortalDataValidationError(
            f"Failed to construct StudentProfileData: {exc}"
        ) from exc

    return ProfilePageResult(
        profile=profile,
        warnings=tuple(warnings)
    )

