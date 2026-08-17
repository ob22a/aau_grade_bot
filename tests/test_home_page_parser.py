"""Regression tests for home page parser with fixture-based validation."""

from pathlib import Path

import pytest

from parser.home import parse_profile_page
from parser.models import ProfilePageResult, StudentProfileData
from clients.aau_portal import PortalSchemaChangedError, PortalDataValidationError


def test_parse_valid_home_page():
    """Test parsing well-formed home page with complete profile fixture."""
    html = (Path("tests/fixtures/portal") / "home_page.html").read_text(encoding="utf-8")
    result = parse_profile_page(html)

    assert isinstance(result, ProfilePageResult)
    assert isinstance(result.profile, StudentProfileData)

    # Fixture doesn't include campus/section so warnings expected
    assert len(result.warnings) == 2
    assert all(w.page_kind == "home" for w in result.warnings)

    # Validate extracted data
    assert result.profile.full_name == "ABEBE KEBEDE AYELE"
    assert result.profile.student_id == "UGR/0000/16"
    assert result.profile.department == "School of information technology and Engineering 2024"
    assert result.profile.year_level == "Year III"
    assert result.profile.campus is None  # Not in fixture
    assert result.profile.section is None  # Not in fixture


def test_profile_data_immutable():
    """Verify profile data is frozen (immutable)."""
    html = (Path("tests/fixtures/portal") / "home_page.html").read_text(encoding="utf-8")
    result = parse_profile_page(html)

    with pytest.raises(Exception):  # Frozen model raises on mutation
        result.profile.full_name = "Modified Name"  # type: ignore


def test_missing_profile_heading_raises_schema_error():
    """Test that missing profile heading triggers schema error."""
    html = """
    <html>
    <div class="widget stacked">
        <div class="widget-content">
            <table>
                <tbody>
                    <tr><td><strong>Full Name</strong></td><td>JOHN DOE</td></tr>
                    <tr><td><strong>ID No.</strong></td><td>STU/0001/25</td></tr>
                    <tr><td><strong>Department</strong></td><td>Engineering</td></tr>
                    <tr><td><strong>Year</strong></td><td>Year II</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    </html>
    """

    with pytest.raises(PortalSchemaChangedError):
        parse_profile_page(html)


def test_missing_profile_widget_raises_schema_error():
    """Test that missing widget structure triggers schema error."""
    html = """
    <html>
    <span class="list-group-item active">My Profile</span>
    <div class="other">
        <table>
            <tbody>
                <tr><td><strong>Full Name</strong></td><td>JOHN DOE</td></tr>
            </tbody>
        </table>
    </div>
    </html>
    """

    with pytest.raises(PortalSchemaChangedError):
        parse_profile_page(html)


def test_missing_profile_table_raises_schema_error():
    """Test that missing table structure triggers schema error."""
    html = """
    <html>
    <div class="widget stacked">
        <span class="list-group-item active">My Profile</span>
        <div class="widget-content">
            <div>No table here</div>
        </div>
    </div>
    </html>
    """

    with pytest.raises(PortalSchemaChangedError):
        parse_profile_page(html)


def test_missing_full_name_raises_error():
    """Test that missing full name triggers validation error."""
    html = """
    <html>
    <div class="widget stacked">
        <span class="list-group-item active">My Profile</span>
        <div class="widget-content">
            <table>
                <tbody>
                    <tr><td><strong>ID No.</strong></td><td>STU/0001/25</td></tr>
                    <tr><td><strong>Department</strong></td><td>Engineering</td></tr>
                    <tr><td><strong>Year</strong></td><td>Year II</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_profile_page(html)


def test_missing_student_id_raises_error():
    """Test that missing student ID triggers validation error."""
    html = """
    <html>
    <div class="widget stacked">
        <span class="list-group-item active">My Profile</span>
        <div class="widget-content">
            <table>
                <tbody>
                    <tr><td><strong>Full Name</strong></td><td>JOHN DOE</td></tr>
                    <tr><td><strong>Department</strong></td><td>Engineering</td></tr>
                    <tr><td><strong>Year</strong></td><td>Year II</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_profile_page(html)


def test_missing_department_raises_error():
    """Test that missing department triggers validation error."""
    html = """
    <html>
    <div class="widget stacked">
        <span class="list-group-item active">My Profile</span>
        <div class="widget-content">
            <table>
                <tbody>
                    <tr><td><strong>Full Name</strong></td><td>JOHN DOE</td></tr>
                    <tr><td><strong>ID No.</strong></td><td>STU/0001/25</td></tr>
                    <tr><td><strong>Year</strong></td><td>Year II</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_profile_page(html)


def test_missing_year_raises_error():
    """Test that missing year level triggers validation error."""
    html = """
    <html>
    <div class="widget stacked">
        <span class="list-group-item active">My Profile</span>
        <div class="widget-content">
            <table>
                <tbody>
                    <tr><td><strong>Full Name</strong></td><td>JOHN DOE</td></tr>
                    <tr><td><strong>ID No.</strong></td><td>STU/0001/25</td></tr>
                    <tr><td><strong>Department</strong></td><td>Engineering</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_profile_page(html)


def test_profile_with_optional_fields():
    """Test profile parsing with campus and section fields."""
    html = """
    <html>
    <div class="widget stacked">
        <span class="list-group-item active">My Profile</span>
        <div class="widget-content">
            <table>
                <tbody>
                    <tr><td><strong>Full Name</strong></td><td>JOHN DOE</td></tr>
                    <tr><td><strong>ID No.</strong></td><td>STU/0001/25</td></tr>
                    <tr><td><strong>Department</strong></td><td>Engineering</td></tr>
                    <tr><td><strong>Year</strong></td><td>Year II</td></tr>
                    <tr><td><strong>Campus</strong></td><td>Main Campus</td></tr>
                    <tr><td><strong>Section</strong></td><td>Section A</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    </html>
    """

    result = parse_profile_page(html)

    assert result.profile.full_name == "JOHN DOE"
    assert result.profile.student_id == "STU/0001/25"
    assert result.profile.department == "Engineering"
    assert result.profile.year_level == "Year II"
    assert result.profile.campus == "Main Campus"
    assert result.profile.section == "Section A"
    assert result.warnings == ()


def test_profile_missing_optional_fields_generates_warnings():
    """Test that optional fields generate warnings when missing."""
    html = """
    <html>
    <div class="widget stacked">
        <span class="list-group-item active">My Profile</span>
        <div class="widget-content">
            <table>
                <tbody>
                    <tr><td><strong>Full Name</strong></td><td>JANE SMITH</td></tr>
                    <tr><td><strong>ID No.</strong></td><td>STU/0002/24</td></tr>
                    <tr><td><strong>Department</strong></td><td>Medicine</td></tr>
                    <tr><td><strong>Year</strong></td><td>Year I</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    </html>
    """

    result = parse_profile_page(html)

    assert len(result.warnings) == 2  # campus and section missing
    assert all(w.page_kind == "home" for w in result.warnings)
    assert result.profile.campus is None
    assert result.profile.section is None

