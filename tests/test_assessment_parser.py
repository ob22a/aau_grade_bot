"""Regression tests for assessment detail modal parser."""

from pathlib import Path

import pytest

from parser.assessment import parse_assessment_details
from parser.models import AssessmentDetailsResult, AssessmentDetails
from clients.aau_portal import PortalSchemaChangedError, PortalDataValidationError


def test_parse_valid_assessment_modal():
    """Test parsing well-formed assessment modal with complete details."""
    html = (Path("tests/fixtures/portal") / "assessment_modal.html").read_text(encoding="utf-8")
    result = parse_assessment_details(html)

    assert isinstance(result, AssessmentDetailsResult)
    assert isinstance(result.assessment, AssessmentDetails)
    assert result.warnings == ()

    # Validate extracted data
    assert result.assessment.course_name == "Operating Systems and System Programming"
    assert len(result.assessment.scores) == 2

    # First score
    assert result.assessment.scores[0].sequence == 1
    assert result.assessment.scores[0].name == "Final Exam ( 50% )"
    assert result.assessment.scores[0].score == 50.0

    # Second score
    assert result.assessment.scores[1].sequence == 2
    assert result.assessment.scores[1].name == "Projects and Exam ( 50% )"
    assert result.assessment.scores[1].score == 48.0

    # Total
    assert result.assessment.total_mark == 98.0
    assert result.assessment.total_possible == 100.0


def test_assessment_data_immutable():
    """Verify assessment data is frozen (immutable)."""
    html = (Path("tests/fixtures/portal") / "assessment_modal.html").read_text(encoding="utf-8")
    result = parse_assessment_details(html)

    with pytest.raises(Exception):  # Frozen model raises on mutation
        result.assessment.course_name = "Modified Course"  # type: ignore


def test_missing_modal_table_raises_schema_error():
    """Test that missing modal table triggers schema error."""
    html = """
    <html>
    <body>
        <div>No table here</div>
    </body>
    </html>
    """

    with pytest.raises(PortalSchemaChangedError):
        parse_assessment_details(html)


def test_missing_table_body_raises_schema_error():
    """Test that missing tbody triggers schema error."""
    html = """
    <html>
    <body>
        <table class="table table-bordered table-striped">
            <thead><tr><th>Header</th></tr></thead>
        </table>
    </body>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_assessment_details(html)


def test_empty_table_raises_validation_error():
    """Test that empty table triggers validation error."""
    html = """
    <html>
    <body>
        <table class="table table-bordered table-striped">
            <tbody></tbody>
        </table>
    </body>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_assessment_details(html)


def test_missing_course_name_raises_error():
    """Test that missing course name triggers validation error."""
    html = """
    <html>
    <body>
        <table class="table table-bordered table-striped">
            <tbody>
                <tr><td colspan="3">No course name</td></tr>
                <tr><td>1</td><td>Assessment 1</td><td>50</td></tr>
                <tr><th colspan="3">Total Mark : 50 / 100</th></tr>
            </tbody>
        </table>
    </body>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_assessment_details(html)


def test_missing_scores_raises_error():
    """Test that missing assessment scores triggers validation error."""
    html = """
    <html>
    <body>
        <table class="table table-bordered table-striped">
            <tbody>
                <tr><td colspan="3">Course : Test Course</td></tr>
                <tr><th>Total Mark : 0 / 100</th></tr>
            </tbody>
        </table>
    </body>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_assessment_details(html)


def test_missing_total_mark_raises_error():
    """Test that missing total mark triggers validation error."""
    html = """
    <html>
    <body>
        <table class="table table-bordered table-striped">
            <tbody>
                <tr><td colspan="3">Course : Test Course</td></tr>
                <tr><td>1</td><td>Assessment 1</td><td>50</td></tr>
            </tbody>
        </table>
    </body>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_assessment_details(html)


def test_malformed_assessment_row_raises_error():
    """Test that malformed assessment row triggers validation error."""
    html = """
    <html>
    <body>
        <table class="table table-bordered table-striped">
            <tbody>
                <tr><td colspan="3">Course : Test Course</td></tr>
                <tr><td>invalid</td><td>Assessment</td><td>score</td></tr>
                <tr><th colspan="3">Total Mark : 50 / 100</th></tr>
            </tbody>
        </table>
    </body>
    </html>
    """

    with pytest.raises(PortalDataValidationError):
        parse_assessment_details(html)


def test_multiple_assessment_scores():
    """Test parsing multiple assessment scores."""
    html = """
    <html>
    <body>
        <table class="table table-bordered table-striped table-hover">
            <tbody>
                <tr class="text-primary">
                    <th colspan="3">Course : Data Structures and Algorithms</th>
                </tr>
                <tr class="success">
                    <th>S.No.</th>
                    <th>Assessment</th>
                    <th>Result</th>
                </tr>
                <tr>
                    <td>1</td>
                    <td>Quiz 1 ( 20% )</td>
                    <td>18</td>
                </tr>
                <tr>
                    <td>2</td>
                    <td>Assignment ( 30% )</td>
                    <td>28</td>
                </tr>
                <tr>
                    <td>3</td>
                    <td>Final Exam ( 50% )</td>
                    <td>45</td>
                </tr>
                <tr class="success">
                    <th colspan="3" style="text-align: right;">
                        Total Mark : 91 / 100
                    </th>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """

    result = parse_assessment_details(html)

    assert result.assessment.course_name == "Data Structures and Algorithms"
    assert len(result.assessment.scores) == 3

    assert result.assessment.scores[0].sequence == 1
    assert result.assessment.scores[0].name == "Quiz 1 ( 20% )"
    assert result.assessment.scores[0].score == 18.0

    assert result.assessment.scores[1].sequence == 2
    assert result.assessment.scores[1].name == "Assignment ( 30% )"
    assert result.assessment.scores[1].score == 28.0

    assert result.assessment.scores[2].sequence == 3
    assert result.assessment.scores[2].name == "Final Exam ( 50% )"
    assert result.assessment.scores[2].score == 45.0

    assert result.assessment.total_mark == 91.0
    assert result.assessment.total_possible == 100.0


def test_course_name_with_underscore_suffix():
    """Test parsing course name with trailing underscore."""
    html = """
    <html>
    <body>
        <table class="table table-bordered table-striped">
            <tbody>
                <tr><td colspan="3">Course : Web Design and Programming_r</td></tr>
                <tr><td>1</td><td>Project ( 100% )</td><td>95</td></tr>
                <tr><th colspan="3">Total Mark : 95 / 100</th></tr>
            </tbody>
        </table>
    </body>
    </html>
    """

    result = parse_assessment_details(html)

    # Course name parser strips the suffix correctly
    assert "Web Design and Programming" in result.assessment.course_name

